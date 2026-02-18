# apps/dashboard/templatetags/dashboard_tags.py

from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(value, arg):
    """
    Безопасное получение значения из словаря по ключу.
    Работает с любыми ключами, включая кириллицу и символы.
    """
    try:
        if isinstance(value, dict):
            # Пробуем разные варианты ключей
            if arg in value:
                val = value[arg]
            elif arg.replace('_', ' ') in value:  # Заменяем подчеркивания на пробелы
                val = value[arg.replace('_', ' ')]
            elif arg.replace(' ', '_') in value:  # И наоборот
                val = value[arg.replace(' ', '_')]
            else:
                # Ищем по нестрогому совпадению
                for key in value.keys():
                    if str(key).strip().lower() == str(arg).strip().lower():
                        val = value[key]
                        break
                else:
                    return ''
            
            # Форматируем Decimal числа
            if hasattr(val, 'as_tuple'):  # Это Decimal
                return f"{float(val):.2f}" if val % 1 else f"{int(val)}"
            return val
        
        return ''
    except Exception:
        return ''