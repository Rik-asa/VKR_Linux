#apps\core\db_utils.py

"""
Утилиты для работы с БД, которые можно использовать ПОСЛЕ инициализации Django
"""

from django.db import connection
from django.utils import timezone
from django.core.cache import cache

def get_months_from_db():
    """
    Получает список месяцев из таблицы kpi.months
    МОЖНО вызывать только после полной инициализации Django!
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT month_number, name 
            FROM kpi.months 
            ORDER BY month_number
        """)
        return cursor.fetchall()

def get_month_name(month_number):
    """Получает название месяца по номеру"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM kpi.months WHERE month_number = %s",
                [month_number]
            )
            result = cursor.fetchone()
            return result[0] if result else f"Месяц {month_number}"
    except Exception as e:
        # Если что-то пошло не так, возвращаем просто номер
        return f"Месяц {month_number}"

def get_all_active_rules():
    """
    Получает все активные правила из таблицы performance_grades
    Возвращает список словарей с ключами: min_percent, max_percent, color
    """
    today = timezone.now().date()
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                min_percent,
                max_percent,
                color
            FROM kpi.performance_grades
            WHERE 
                valid_from <= %s
                AND (valid_to IS NULL OR valid_to >= %s)
            ORDER BY min_percent
        """, [today, today])
        
        rules = []
        for row in cursor.fetchall():
            rules.append({
                'min_percent': float(row[0]),
                'max_percent': float(row[1]) if row[1] is not None else None,
                'color': row[2]
            })
        return rules


def get_color_for_percentage(percentage, rules_cache=None):
    """
    Возвращает цвет для процента на основе правил
    Если rules_cache передан - использует его, иначе загружает правила заново
    """
    if percentage is None:
        return None
    
    if rules_cache is None:
        rules_cache = get_all_active_rules()
    
    for rule in rules_cache:
        min_p = rule['min_percent']
        max_p = rule['max_percent']
        
        if min_p <= percentage:
            if max_p is None or percentage <= max_p:
                return rule['color']
    
    return None