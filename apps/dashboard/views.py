# apps/dashboard/views.py

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.utils import timezone
from datetime import datetime
from apps.core.db_utils import get_months_from_db, get_month_name
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt


@login_required
def dashboard_home(request):
    """Главная страница дашборда с редиректом в зависимости от роли."""
    
    # Если не заведующий и не админ - редирект на данные врача
    if not (request.user.is_accountant() or request.user.is_superuser):
        return redirect('unified_plan_fact')

    # Параметры из GET-запроса
    year = request.GET.get('year', datetime.now().year)
    month = request.GET.get('month', datetime.now().month)

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        year = datetime.now().year
        month = datetime.now().month
    
    # Получаем данные для диаграмм из PostgreSQL функций
    top_doctors = []
    specialization_stats = []
    
    # Получаем топ-5 врачей по выполнению плана
    # Загружаем правила для цветов один раз
    
    from apps.core.db_utils import get_all_active_rules, get_color_for_percentage
    color_rules = get_all_active_rules()
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT 
                    doctor_name,
                    specialization,
                    avg_percentage
                FROM kpi.get_top_doctors(%s, %s, 6)
            """
            cursor.execute(query, [year, month])
            results = cursor.fetchall()

            # Преобразуем результаты в список кортежей
            for row in results:
                doctor_name = row[0] if row[0] else None
                specialization = row[1] if row[1] else None
                avg_percentage = float(row[2]) if row[2] is not None else 0.0
                color = get_color_for_percentage(avg_percentage, color_rules)

                top_doctors.append({
                    'name': doctor_name,
                    'specialization': specialization,
                    'percentage': avg_percentage,
                    'color': color
                })
                
    except Exception as e:
        print(f"Ошибка при получении топ-врачей: {e}")
        top_doctors = []

    # Получаем статистику по специальностям
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT 
                    specialization,
                    doctor_count,
                    avg_percentage,
                    total_plan,
                    total_fact
                FROM kpi.get_specialization_stats(%s, %s)
            """
            cursor.execute(query, [year, month])
            results = cursor.fetchall()

            for row in results:
                specialization = row[0] if row[0] else None
                doctor_count = row[1] if row[1] is not None else 0
                avg_percentage = float(row[2]) if row[2] is not None else 0.0
                total_plan = float(row[3]) if row[3] is not None else 0.0
                total_fact = row[4] if row[4] is not None else 0
                color = get_color_for_percentage(avg_percentage, color_rules)

                specialization_stats.append({
                    'name': specialization,
                    'doctor_count': doctor_count,
                    'percentage': avg_percentage,
                    'total_plan': total_plan,
                    'total_fact': total_fact,
                    'color': color
                })
                
    except Exception as e:
        print(f"Ошибка при получении статистики по специальностям: {e}")
        specialization_stats = []

    months_data = get_months_from_db()

    context = {
        'year': year,
        'month': month,
        'top_doctors': top_doctors,
        'specialization_stats': specialization_stats,
        'months': months_data,
        'years': range(2025, datetime.now().year + 1),
        'current_user': request.user,
    }
    
    return render(request, 'dashboard/accountant_dashboard.html', context)

#умная фильтрация
@login_required
def unified_plan_fact(request):
    """
    УНИВЕРСАЛЬНАЯ страница отчетов.
    Все настройки берутся из БД (таблицы reports, report_filters, filter_types)
    """
    user = request.user
    
    # 1. Получаем все активные отчеты
    with connection.cursor() as cursor:
        query = """
            SELECT id, report_code, report_name, sql_function_name
            FROM kpi.reports
            WHERE is_active = true
        """
        if not (user.is_accountant() or user.is_superuser):
            query += " AND available_for_doctors = true"
        query += " ORDER BY sort_order"
        cursor.execute(query)

        reports = []
        for row in cursor.fetchall():
            reports.append({
                'id': row[0],
                'code': row[1],
                'name': row[2],
                'func': row[3]
            })
    
    if not reports:
        return render(request, 'dashboard/access_denied.html', {
            'message': 'В системе не настроено ни одного отчета'
        })
    
    # 2. Определяем текущий отчет (из GET или первый)
    try:
        current_report_id = int(request.GET.get('report_id', reports[0]['id']))
    except (ValueError, TypeError):
        current_report_id = reports[0]['id']
    
    # Находим текущий отчет в списке
    current_report = None
    for r in reports:
        if r['id'] == current_report_id:
            current_report = r
            break
    
    if not current_report:
        current_report = reports[0]
        current_report_id = reports[0]['id']
    
    # 3. Получаем настройки фильтров для текущего отчета
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                ft.filter_code,
                ft.display_name,
                ft.sql_query,
                ft.value_field,
                ft.text_field,
                ft.ui_element,
                ft.input_type,
                ft.min_value,
                ft.max_value,
                ft.is_multiple,
                ft.is_optional,
                rf.param_name,
                rf.default_value,
                rf.is_required
            FROM kpi.report_filters rf
            JOIN kpi.filter_types ft ON rf.filter_type_id = ft.id
            WHERE rf.report_id = %s
            ORDER BY rf.display_order
        """, [current_report_id])
        
        filters_config = cursor.fetchall()
    
    def evaluate_default(value):
        """Пытается выполнить значение как SQL, если не получается - возвращает как строку"""
        if not value or not isinstance(value, str):
            return value
        
        clean_value = value.strip()
        
        # Пробуем выполнить как SQL
        try:
            with connection.cursor() as cursor:
                cursor.execute(clean_value)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    result = str(row[0])
                    return result
                return None
        except Exception as e:
            # Если не SQL или ошибка - возвращаем как есть
            return clean_value

    # === ВЫЧИСЛЯЕМ ВСЕ DEFAULT_VALUE ОДИН РАЗ ===
    defaults_cache = {}
    for fc in filters_config:
        filter_code = fc[0]
        default_value = fc[12]
        defaults_cache[filter_code] = evaluate_default(default_value) if default_value else None
    
    # 4. Собираем данные для фильтров (для шаблона)
    filters_for_template = []
    
    for fc in filters_config:
        filter_code = fc[0]
        filter_info = {
            'code': filter_code,      # filter_code
            'name': fc[1],            # display_name
            'ui_element': fc[5],      # ui_element
            'input_type': fc[6],      # input_type
            'min': fc[7],             # min_value
            'max': fc[8],             # max_value
            'multiple': fc[9],        # is_multiple
            'optional': fc[10],       # is_optional
            'param_name': fc[11],     # param_name
            'default': defaults_cache.get(filter_code),        # default_value
            'required': fc[13],       # is_required
            'options': []              # варианты для select/checkbox
        }

        # Если это фильтр со списком значений
        if fc[2] and fc[2].strip():
            try:
                with connection.cursor() as cursor2:
                    cursor2.execute(fc[2])
                    filter_info['options'] = [
                        {'value': row[0], 'text': row[1]}
                        for row in cursor2.fetchall()
                    ]
            except Exception as e:
                filter_info['options'] = []
        
        filters_for_template.append(filter_info)

    # === СБОР ЗНАЧЕНИЙ ФИЛЬТРОВ (ТОЛЬКО ОДИН РАЗ) ===
    filter_values = {}
    
    for fc in filters_config:
        param_name = fc[11]  # param_name (p_year, p_month и т.д.)
        filter_code = fc[0]   # filter_code (year, month и т.д.)
        is_multiple = fc[9]    # is_multiple
        default_value = fc[12]   # default_value
        is_required = fc[13]     # is_required
        evaluated_default = defaults_cache.get(filter_code)
        
        if is_multiple:
            values = request.GET.getlist(filter_code)
            if values:
                filter_values[param_name] = values
            elif evaluated_default and is_required:
                filter_values[param_name] = [evaluated_default]
        else:
            value = request.GET.get(filter_code)
            if value:
                filter_values[param_name] = value
            elif evaluated_default and is_required:
                filter_values[param_name] = evaluated_default
    
    # Если пользователь - врач (не заведующий и не суперюзер)
    if not (user.is_accountant() or user.is_superuser):
        # Проверяем, есть ли в этом отчете фильтр по врачу
        has_doctor_filter = any(fc[0] == 'doctor' for fc in filters_config)
        
        if has_doctor_filter and user.manid:
            # Принудительно подставляем ID врача
            filter_values['p_man_id'] = user.manid

    # === ВЫЗОВ SQL ФУНКЦИИ ===
    data = []
    columns = []
    
    try:
        # Преобразуем в JSON
        filter_json = json.dumps(filter_values, ensure_ascii=False)
        
        # Вызываем функцию
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {current_report['func']}(%s)",
                [filter_json]
            )
            
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i]
                    data.append(row_dict)

    except Exception as e:
        import traceback
        traceback.print_exc()
    
    # Получаем дату последней синхронизации (как в dynamic_dashboard)
    last_sync = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT solution_med.import_date()")
            row = cursor.fetchone()
            if row and row[0]:
                last_sync = row[0]
    except Exception as e:
        print(f"Ошибка получения даты синхронизации: {e}")
        last_sync = None

    # 5. Контекст для шаблона
    context = {
        'reports': reports,
        'current_report_id': current_report_id,
        'current_report': current_report,
        'filters': filters_for_template,
        'columns': columns,
        'data': data,
        'current_user': user,
        'is_doctor_user': not (user.is_accountant() or user.is_superuser),
        'months': get_months_from_db(),
        'years': range(2025, datetime.now().year + 2),
        'last_sync': last_sync,
    }
    
    return render(request, 'dashboard/dynamic_comparison.html', context)

def smart_redirect(request):
    """
    Умное перенаправление после логина или с главной.
    - Врачи → сразу на их данные
    - Заведующие → на общую статистику
    """
    if not request.user.is_authenticated:
        # Не авторизован → на логин
        from django.shortcuts import redirect
        return redirect('login')
    
    # Определяем куда отправлять
    if request.user.is_accountant() or request.user.is_superuser:
        # Заведующие/админы → на новый динамический дашборд
        from django.shortcuts import redirect
        return redirect('dynamic_dashboard')
    else:
        # Врачи → на единую страницу (их данные)
        from django.shortcuts import redirect
        return redirect('plan_fact')

def get_report_config(request):
    """Получить конфигурацию фильтров для отчета"""
    report_id = request.GET.get('report_id')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                ft.filter_code,
                ft.display_name,
                ft.ui_element,
                ft.input_type,
                ft.min_value,
                ft.max_value,
                ft.is_multiple,
                ft.is_optional,
                COALESCE(
                    (SELECT json_agg(json_build_object('value', value_field, 'text', text_field))
                     FROM (SELECT value_field, text_field FROM ... WHERE filter_type_id = ft.id) as opts),
                    '[]'::json
                ) as options
            FROM kpi.report_filters rf
            JOIN kpi.filter_types ft ON rf.filter_type_id = ft.id
            WHERE rf.report_id = %s
            ORDER BY rf.display_order
        """, [report_id])
        
        filters = []
        for row in cursor.fetchall():
            filters.append({
                'code': row[0],
                'name': row[1],
                'ui_element': row[2],
                'input_type': row[3],
                'min': row[4],
                'max': row[5],
                'multiple': row[6],
                'optional': row[7],
                'options': row[8] or []
            })
    
    return JsonResponse({'filters': filters})

def get_report_data(request):
    """API для получения данных отчета"""
    try:
        report_id = request.GET.get('report_id')
        
        # Получаем функцию отчета из БД
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sql_function_name 
                FROM kpi.reports 
                WHERE id = %s
            """, [report_id])
            result = cursor.fetchone()
            if not result:
                return JsonResponse({'success': False, 'error': 'Отчет не найден'})
            
            func_name = result[0]
        
        # Собираем все параметры из GET в JSON
        params = {}
        for key, value in request.GET.items():
            if key != 'report_id':
                # Проверяем, может ли это быть массивом
                if key in request.GET.getlist(key) and len(request.GET.getlist(key)) > 1:
                    params[key] = request.GET.getlist(key)
                else:
                    params[key] = value
        
        # Вызываем функцию
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {func_name}(%s)", [json.dumps(params)])
            
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                data = []
                for row in cursor.fetchall():
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i]
                    data.append(row_dict)
                
                return JsonResponse({
                    'success': True,
                    'columns': columns,
                    'data': data
                })
            else:
                return JsonResponse({
                    'success': True,
                    'columns': [],
                    'data': []
                })
                
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def dynamic_dashboard(request):
    """Новый динамический дашборд (настраивается через БД)"""
    from django.db import connection
    from datetime import datetime
    import json
    
    # Если не заведующий и не админ - редирект на данные врача
    if not (request.user.is_accountant() or request.user.is_superuser):
        return redirect('plan_fact')
    
    # Получаем активный дашборд
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, code, name
            FROM kpi.dashboards
            WHERE is_active = true
            ORDER BY sort_order
            LIMIT 1
        """)
        dashboard = cursor.fetchone()
    
    if not dashboard:
        return render(request, 'dashboard/access_denied.html', {
            'message': 'Дашборд не настроен. Обратитесь к администратору.'
        })
    
    dashboard_id, dashboard_code, dashboard_name = dashboard
    
    # Получаем виджеты дашборда
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT code, name, widget_type, chart_type,
                   sql_function_name, sql_params,
                   x_field, y_field, limit_records, width, height
            FROM kpi.dashboard_widgets
            WHERE dashboard_id = %s
            ORDER BY sort_order
        """, [dashboard_id])
        widgets = cursor.fetchall()
    
    # Параметры из GET
    p_year = request.GET.get('year', datetime.now().year)
    p_month = request.GET.get('month', datetime.now().month)
    
    try:
        p_year = int(p_year)
        p_month = int(p_month)
    except:
        p_year = datetime.now().year
        p_month = datetime.now().month

    # Получаем дату последней синхронизации
    last_sync = None
    with connection.cursor() as cursor:
        cursor.execute("""
            select solution_med.import_date()
        """)
        row = cursor.fetchone()
        if row and row[0]:
            last_sync = row[0]
    
    # Создаём ключ для кэша (зависит от пользователя, года, месяца)
    cache_key = f'dashboard_{request.user.pk}_{p_year}_{p_month}'
    
    # Пробуем получить данные из кэша
    widgets_data = cache.get(cache_key)

    if widgets_data is None:

        widgets_data = []
        for widget in widgets:
            (code, name, widget_type, chart_type,
            sql_function_name, sql_params,
            x_field, y_field, limit_records, width, height) = widget
            
            params = json.loads(sql_params) if sql_params else {}
            params['p_year'] = p_year
            params['p_month'] = p_month
            
            data = []
            try:
                params_json = json.dumps(params)
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM {sql_function_name}(%s)", [params_json])
                    columns = [col[0] for col in cursor.description]
                    for row in cursor.fetchall():
                        data.append(dict(zip(columns, row)))
                    if limit_records and limit_records > 0:
                        data = data[:limit_records]
            except Exception as e:
                print(f"Ошибка виджета {code}: {e}")
                data = []
            
            labels = []
            values = []
            if data and x_field and y_field:
                labels = [str(row.get(x_field, '')) for row in data]
                values = [float(row.get(y_field, 0)) for row in data]
            
            widgets_data.append({
                'code': code,
                'name': name,
                'type': widget_type,
                'chart_type': chart_type,
                'width': width or 6,
                'height': height or 400,
                'data': data,
                'labels': json.dumps(labels),
                'values': json.dumps(values),
            })
        
        # Сохраняем в кэш на 5 минут
        cache.set(cache_key, widgets_data, 300)
    
    # Месяцы для фильтра
    months = []
    with connection.cursor() as cursor:
        cursor.execute("SELECT month_number, name FROM kpi.months ORDER BY month_number")
        months = cursor.fetchall()
    
    years = range(2024, datetime.now().year + 2)
    
    context = {
        'widgets': widgets_data,
        'year': p_year,
        'month': p_month,
        'months': months,
        'years': years,
        'current_user': request.user,
        'last_sync': last_sync,
    }
    
    return render(request, 'dashboard/dashboard_dynamic.html', context)

def export_current_table_ods(request):
    """Экспорт текущей таблицы в ODS с автошириной колонок"""
    import json
    from datetime import datetime
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell, TableColumn
    from odf.text import P
    from odf.style import Style, TextProperties, ParagraphProperties, TableCellProperties, TableColumnProperties
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Только POST'})
    
    try:
        body = json.loads(request.body)
        headers = body.get('headers', [])
        data = body.get('data', [])
        report_name = body.get('report_name', 'Отчет')
        max_lengths = body.get('max_lengths', [])
        
        if not data or not headers:
            return JsonResponse({'success': False, 'error': 'Нет данных для экспорта'})
        
        # Если max_lengths не переданы, рассчитываем по заголовкам
        if not max_lengths:
            max_lengths = [len(str(h)) for h in headers]
        
        doc = OpenDocumentSpreadsheet()
        border = "0.5pt solid #000000"
        
        # Функция конвертации длины в сантиметры
        def length_to_cm(char_length):
            if char_length <= 10:
                return 2.26
            else:
                width = char_length * 0.18
                return min(10.0, width)
        
        # Стиль для заголовков
        header_style = Style(name="HeaderStyle", family="table-cell")
        header_style.addElement(TextProperties(fontweight="bold", color="#ffffff", fontfamily="Times New Roman"))
        header_style.addElement(ParagraphProperties(textalign="center"))
        header_style.addElement(TableCellProperties(backgroundcolor="#366092", wrapoption="wrap", verticalalign="middle", border=border))
        doc.automaticstyles.addElement(header_style)
        
        # Стиль для чисел
        number_style = Style(name="NumberStyle", family="table-cell")
        number_style.addElement(TextProperties(fontfamily="Times New Roman"))
        number_style.addElement(ParagraphProperties(textalign="end"))
        number_style.addElement(TableCellProperties(wrapoption="wrap", verticalalign="middle", border=border))
        doc.automaticstyles.addElement(number_style)
        
        # Стиль для текста
        text_style = Style(name="TextStyle", family="table-cell")
        text_style.addElement(TextProperties(fontfamily="Times New Roman"))
        text_style.addElement(ParagraphProperties(textalign="start"))
        text_style.addElement(TableCellProperties(wrapoption="wrap", verticalalign="middle", border=border))
        doc.automaticstyles.addElement(text_style)
        
        # Создаем таблицу
        table = Table(name=report_name[:31])
        
        # Устанавливаем ширину колонок на основе максимальной длины
        for idx, (header, max_len) in enumerate(zip(headers, max_lengths)):
            width_cm = length_to_cm(max_len)
            
            col_style = Style(name=f"col_{idx}", family="table-column")
            col_style.addElement(TableColumnProperties(columnwidth=f"{width_cm}cm"))
            doc.automaticstyles.addElement(col_style)
            col = TableColumn(stylename=col_style)
            table.addElement(col)
        
        # Функция для проверки, является ли значение числом
        def is_numeric(value):
            if value is None or value == '':
                return False
            try:
                float(str(value).replace(',', '.'))
                return True
            except ValueError:
                return False
        
        # Заголовки
        header_row = TableRow()
        for header in headers:
            cell = TableCell(stylename=header_style)
            cell.addElement(P(text=str(header)))
            header_row.addElement(cell)
        table.addElement(header_row)
        
        # Данные
        for row_data in data:
            table_row = TableRow()
            for header in headers:
                value = row_data.get(header, '')
                
                if is_numeric(value):
                    cell_style = number_style
                    try:
                        num = float(str(value).replace(',', '.'))
                        if num.is_integer():
                            display_value = str(int(num))
                        else:
                            display_value = str(round(num, 2)).replace('.', ',')
                    except:
                        display_value = str(value)
                else:
                    cell_style = text_style
                    display_value = str(value) if value else ''
                
                cell = TableCell(stylename=cell_style)
                cell.addElement(P(text=display_value))
                table_row.addElement(cell)
            table.addElement(table_row)
        
        doc.spreadsheet.addElement(table)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = ''.join(c for c in report_name if c.isalnum() or c in '._- ')[:50]
        filename = f"{safe_name}_{timestamp}.ods"
        
        response = HttpResponse(
            content_type='application/vnd.oasis.opendocument.spreadsheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        doc.save(response)
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})