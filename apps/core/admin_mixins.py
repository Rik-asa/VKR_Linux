# apps/core/admin_mixins.py

from django.db import connection
from django.contrib import admin


class SmartSearchMixin(admin.ModelAdmin):
    """
    Универсальный миксин для поиска по managed=False моделям.
    
    Использование:
        class MyModelAdmin(SmartSearchMixin, admin.ModelAdmin):
            search_fields = ['field1', 'field2']
            search_related_tables = {
                'manid': ('solution_med.import_man', 'text', 'manidmis'),  # (таблица, поле_поиска, поле_связи)
            }
    """
    
    search_related_tables = {}
    
    def get_search_results(self, request, queryset, search_term):
        """
        Расширенный поиск с поддержкой связанных таблиц
        """
        if not search_term:
            return super().get_search_results(request, queryset, search_term)
        
        model = self.model
        db_table = model._meta.db_table
        
        # Очищаем имя таблицы от кавычек
        if '"' in db_table:
            db_table = db_table.replace('"."', '.')
        
        # Собираем условия поиска
        conditions = []
        params = []
        
        # 1. Поиск по обычным полям модели
        for field_name in self.search_fields:
            conditions.append(f"CAST({field_name} AS TEXT) ILIKE %s")
            params.append(f'%{search_term}%')
        
        # 2. Поиск по связанным таблицам
        for model_field, relation_config in self.search_related_tables.items():
            # Поддерживаем два формата:
            # - кортеж из 2 элементов: (таблица, поле_поиска) -> поле_связи = 'keyidmis'
            # - кортеж из 3 элементов: (таблица, поле_поиска, поле_связи)
            if len(relation_config) == 2:
                related_table, related_field = relation_config
                join_field = 'keyidmis'  # по умолчанию
            else:
                related_table, related_field, join_field = relation_config
            
            conditions.append(f"""
                EXISTS (
                    SELECT 1 FROM {related_table}
                    WHERE CAST({related_table}.{related_field} AS TEXT) ILIKE %s
                    AND {db_table}.{model_field} = {related_table}.{join_field}
                )
            """)
            params.append(f'%{search_term}%')
        
        if conditions:
            try:
                with connection.cursor() as cursor:
                    query = f"""
                        SELECT keyid FROM {db_table}
                        WHERE {' OR '.join(conditions)}
                        GROUP BY keyid
                    """
                    cursor.execute(query, params)
                    keyids = [row[0] for row in cursor.fetchall()]
                
                if keyids:
                    queryset = queryset.filter(keyid__in=keyids)
                else:
                    queryset = queryset.none()
                use_distinct = True
            except Exception as e:
                print(f"Search error for {db_table}: {e}")
                queryset = queryset.none()
                use_distinct = True
        else:
            queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        
        return queryset, use_distinct