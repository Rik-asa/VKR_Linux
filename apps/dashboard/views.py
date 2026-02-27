# apps/dashboard/views.py

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.utils import timezone
from datetime import datetime
from apps.core.db_utils import get_months_from_db, get_month_name

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
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT 
                    doctor_name,
                    specialization,
                    avg_percentage
                FROM kpi.get_top_doctors(%s, %s, 5)
            """
            cursor.execute(query, [year, month])
            results = cursor.fetchall()

            # Преобразуем результаты в список кортежей
            for row in results:
                # row = (doctor_name, specialization, avg_percentage)
                doctor_name = row[0] if row[0] else None
                specialization = row[1] if row[1] else None
                avg_percentage = float(row[2]) if row[2] is not None else 0.0
                top_doctors.append((doctor_name, specialization, avg_percentage))
                
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
                specialization_stats.append((specialization, doctor_count, avg_percentage, total_plan, total_fact))
                
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
    ЕДИНАЯ страница сравнения план-факт.
    Рендерит dynamic_comparison.html напрямую.
    """
    user = request.user
    
    # Определяем роль
    is_manager = user.is_accountant() or user.is_superuser

    # ИНИЦИАЛИЗИРУЕМ переменные для всех случаев
    doctor_man_id = None
    doctor_name = ""
    
    # Для врача: получаем его данные
    if not is_manager:
        doctor_man_id = user.manid
        if not doctor_man_id:
            return render(request, 'dashboard/access_denied.html', {
                'message': 'У вашего аккаунта не привязан ID врача из МИС'
            })
    
    # Параметры из GET (с умолчаниями)
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    year = request.GET.get('year', current_year)
    month = request.GET.get('month', current_month)
    
    # Конвертация
    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        year = current_year
        month = current_month
    
    # ФИЛЬТРАЦИЯ ПО РОЛИ
    # Для врача: force его man_id
    # Для заведующего: из параметров или None
    if is_manager:
        man_id_param = request.GET.get('man_id', '').strip()
        man_id = int(man_id_param) if man_id_param else None
    else:
        man_id = doctor_man_id  # Автоматически для врача
    
    specid_param = request.GET.get('specid', '').strip()
    
    specid = int(specid_param) if specid_param else None
    stat_purpose_codes = request.GET.getlist('stat_purpose_codes')  # для множественного выбора
    
    # Очищаем от пустых значений
    stat_purpose_codes = [code for code in stat_purpose_codes if code and code.strip()]

    if not stat_purpose_codes or stat_purpose_codes == ['']:
        stat_purpose_codes = None
    
    # Вызов хранимой процедуры
    columns = []
    data = []
    
    try:
        with connection.cursor() as cursor:
            query = "SELECT * FROM kpi.get_monthly_plan_fact_comparison(%s, %s, %s, %s, %s)"
            
            purpose_param = stat_purpose_codes if stat_purpose_codes and stat_purpose_codes != [''] else None
            
            cursor.execute(query, [year, month, man_id, specid, purpose_param])
            
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                results = cursor.fetchall()
            
            # Преобразуем в словари
            for row in results:
                row_dict = {}
                for i, value in enumerate(row):
                    col_name = columns[i] if i < len(columns) else f'col_{i}'
                    row_dict[col_name] = value
                data.append(row_dict)
                
    except Exception as e:
        print(f"❌ Ошибка SQL: {e}")
    
    # ДАННЫЕ ДЛЯ ФИЛЬТРОВ (напрямую из БД)
    doctors_data = []
    specializations_data = []
    purposes_data = []
    
    # Врачи: ТОЛЬКО для заведующих
    if is_manager:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT manidmis, text 
                    FROM solution_med.import_man 
                    WHERE text IS NOT NULL 
                    ORDER BY text
                """)
                for row in cursor.fetchall():
                    doctors_data.append({
                        'id': row[0],
                        'name': row[1]
                    })
        except Exception:
            pass
    
    # Специальности: для всех
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT keyidmis, text, code 
                FROM kpi.specialities 
                ORDER BY text
            """)
            for row in cursor.fetchall():
                specializations_data.append({
                    'id': row[0],
                    'name': f"{row[1]} "
                })
    except Exception:
        pass
    
    # Цели: для всех
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT stat_purpose_code, stat_purpose_name
                FROM kpi.stat_purpose_mapping
                ORDER BY stat_purpose_name
            """)
            for row in cursor.fetchall():
                purposes_data.append({
                    'id': row[0],
                    'name': f"{row[1]}"
                })
    except Exception:
        pass
    
    # КОНТЕКСТ
    context = {
        # Основные данные
        'year': year,
        'month': month,
        'columns': columns,
        'data': data,
        'total': len(data),

        # Информация о пользователе
        'is_doctor_user': not is_manager,
        'current_user': user,

        # Если нужно передать имя врача для отображения
        'doctor_name': doctor_name if not is_manager else None,
        'doctor_id': doctor_man_id if not is_manager else None,
        

        # Фильтры
        'form_filters': {
            'man_id': str(man_id) if man_id else '',
            'specid': str(specid) if specid else '',
            'stat_purpose_codes': stat_purpose_codes if stat_purpose_codes else [], 
        },

        # Фильтры
        'doctors': doctors_data,
        'specializations': specializations_data,
        'purposes': purposes_data,
        
        # Списки
        'months': get_months_from_db(),
        'years': range(2025, datetime.now().year + 2),
        
        # Заголовок страницы
        'page_title': 'Сравнение план-факт' if is_manager else 'Мои показатели',
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