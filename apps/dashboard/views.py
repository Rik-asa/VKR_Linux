# apps/dashboard/views.py

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.utils import timezone
from datetime import datetime
from apps.core.db_utils import get_months_from_db, get_month_name
from django.http import JsonResponse

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
    
    # 4. Собираем данные для фильтров (для шаблона)
    filters_for_template = []
    
    for fc in filters_config:
        filter_info = {
            'code': fc[0],           # filter_code
            'name': fc[1],            # display_name
            'ui_element': fc[5],      # ui_element
            'input_type': fc[6],      # input_type
            'min': fc[7],             # min_value
            'max': fc[8],             # max_value
            'multiple': fc[9],        # is_multiple
            'optional': fc[10],       # is_optional
            'param_name': fc[11],     # param_name
            'default': fc[12],        # default_value
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
                print(f"Ошибка при загрузке фильтра {fc[0]}: {e}")
                filter_info['options'] = []
        
        filters_for_template.append(filter_info)

    # === СБОР ЗНАЧЕНИЙ ФИЛЬТРОВ (ТОЛЬКО ОДИН РАЗ) ===
    filter_values = {}
    
    for fc in filters_config:
        param_name = fc[11]  # param_name (p_year, p_month и т.д.)
        filter_code = fc[0]   # filter_code (year, month и т.д.)
        is_multiple = fc[9]    # is_multiple
        
        if is_multiple:
            values = request.GET.getlist(filter_code)
            if values:
                filter_values[param_name] = values
        else:
            value = request.GET.get(filter_code)
            if value:
                filter_values[param_name] = value
    
    # Если пользователь - врач (не заведующий и не суперюзер)
    if not (user.is_accountant() or user.is_superuser):
        # Проверяем, есть ли в этом отчете фильтр по врачу
        has_doctor_filter = any(fc[0] == 'doctor' for fc in filters_config)
        
        if has_doctor_filter and user.manid:
            # Принудительно подставляем ID врача
            filter_values['p_man_id'] = user.manid
    
    # Если есть год и месяц в фильтрах, убедимся что они есть
    if 'year' in [fc[0] for fc in filters_config] and 'p_year' not in filter_values:
        filter_values['p_year'] = datetime.now().year
    if 'month' in [fc[0] for fc in filters_config] and 'p_month' not in filter_values:
        filter_values['p_month'] = datetime.now().month
    
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
        # Заведующие/админы → на dashboard_home
        from django.shortcuts import redirect
        return redirect('dashboard_home')
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