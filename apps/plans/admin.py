# apps/plans/admin.py

from django.contrib import admin
from django import forms
from django.db import connection
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import path
from django.http import HttpResponse
import csv
import io

# ==================== МОДЕЛЬ ====================
from django.db import models

class KpiPlan(models.Model):
    """Минимальная модель для админки"""
    keyid = models.BigAutoField(primary_key=True)
    specid = models.IntegerField(verbose_name='ID специальности')
    plan_vistype = models.IntegerField(verbose_name='ID цели визита')
    plan_value = models.IntegerField(verbose_name='Плановое значение')
    year = models.IntegerField(verbose_name='Год')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'kpi"."plans'
        unique_together = [['year', 'specid', 'plan_vistype']]
        verbose_name = 'План KPI'
        verbose_name_plural = 'Планы KPI'

    def __str__(self):
        return f"{self.year} - {self.get_spec_name()} - {self.get_purpose_name()}"

    def get_spec_name(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT text FROM kpi.specialities WHERE keyidmis = %s",
                [self.specid]
            )
            result = cursor.fetchone()
            return result[0] if result else f"ID: {self.specid}"

    def get_purpose_name(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT text FROM kpi.purposes WHERE code = %s",
                [self.plan_vistype]
            )
            result = cursor.fetchone()
            return result[0] if result else f"Цель: {self.plan_vistype}"

    def monthly_plan(self):
        import math
        return math.floor(self.plan_value / 12)


# ==================== ФОРМА ====================
class KpiPlanForm(forms.ModelForm):
    class Meta:
        model = KpiPlan
        fields = ['year', 'specid', 'plan_vistype', 'plan_value']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Загружаем специальности
        with connection.cursor() as cursor:
            cursor.execute("SELECT keyidmis, text FROM kpi.specialities ORDER BY text")
            spec_choices = [('', '--- Выберите специальность ---')]
            for row in cursor.fetchall():
                spec_choices.append((str(row[0]), row[1]))
            self.fields['specid'].widget = forms.Select(choices=spec_choices)
        
        # Загружаем цели
        with connection.cursor() as cursor:
            cursor.execute("SELECT code, text FROM kpi.purposes ORDER BY text")
            purpose_choices = [('', '--- Выберите цель визита ---')]
            for row in cursor.fetchall():
                purpose_choices.append((str(row[0]), row[1]))
            self.fields['plan_vistype'].widget = forms.Select(choices=purpose_choices)
        
        self.fields['specid'].label = 'Специальность'
        self.fields['plan_vistype'].label = 'Цель визита'
        self.fields['plan_value'].label = 'Плановое значение (год)'
        self.fields['year'].label = 'Год'


# ==================== АДМИНКА ====================
@admin.register(KpiPlan)
class KpiPlanAdmin(admin.ModelAdmin):
    form = KpiPlanForm
    list_display = ['year', 'get_spec_name', 'get_purpose_name', 'plan_value', 'monthly_plan_display']
    list_filter = ['year']
    search_fields = ['specid', 'plan_vistype']
    list_editable = ['plan_value']
    actions = ['export_as_csv']

    def get_spec_name(self, obj):
        return obj.get_spec_name()
    get_spec_name.short_description = 'Специальность'
    get_spec_name.admin_order_field = 'specid'

    def get_purpose_name(self, obj):
        return obj.get_purpose_name()
    get_purpose_name.short_description = 'Цель визита'
    get_purpose_name.admin_order_field = 'plan_vistype'

    def monthly_plan_display(self, obj):
        return obj.monthly_plan()
    monthly_plan_display.short_description = 'План на месяц'

    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="plans_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['year', 'specid', 'plan_vistype', 'plan_value', 'spec_name', 'purpose_name'])
        
        for plan in queryset:
            writer.writerow([
                plan.year, plan.specid, plan.plan_vistype, plan.plan_value,
                plan.get_spec_name(), plan.get_purpose_name()
            ])
        
        self.message_user(request, f"Экспортировано {queryset.count()} планов")
        return response
    export_as_csv.short_description = "📥 Экспортировать выбранные в CSV"

    # ===== КАСТОМНЫЕ URL =====
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-csv/', self.import_csv, name='plans_import_csv'),
            path('export-all/', self.export_all, name='plans_export_all'),
            path('bulk-delete/', self.bulk_delete, name='plans_bulk_delete'),
        ]
        return custom_urls + urls

    # ===== ИМПОРТ =====
    def import_csv(self, request):
        if request.method == 'POST':
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                messages.error(request, 'Выберите файл')
                return redirect('..')
            
            try:
                decoded = csv_file.read().decode('utf-8')
                io_string = io.StringIO(decoded)
                reader = csv.DictReader(io_string)
                
                success = 0
                errors = 0
                
                with connection.cursor() as cursor:
                    for row in reader:
                        try:
                            cursor.execute("""
                                INSERT INTO kpi.plans (year, specid, plan_vistype, plan_value)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (year, specid, plan_vistype) 
                                DO UPDATE SET plan_value = EXCLUDED.plan_value,
                                             updated_at = NOW()
                            """, [row['year'], row['specid'], row['plan_vistype'], row['plan_value']])
                            success += 1
                        except Exception:
                            errors += 1
                
                messages.success(request, f'✅ Импорт завершен: {success} добавлено/обновлено, {errors} ошибок')
            except Exception as e:
                messages.error(request, f'❌ Ошибка: {e}')
            
            return redirect('..')
        
        return render(request, 'admin/plans_import.html', {
            'title': 'Импорт планов из CSV',
            'opts': self.model._meta,
        })

    # ===== ЭКСПОРТ ВСЕГО =====
    def export_all(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="all_plans.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['year', 'specid', 'plan_vistype', 'plan_value', 'created_at', 'updated_at'])
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT year, specid, plan_vistype, plan_value, created_at, updated_at FROM kpi.plans ORDER BY year DESC, specid, plan_vistype")
            writer.writerows(cursor.fetchall())
        
        return response

    # ===== МАССОВОЕ УДАЛЕНИЕ =====
    def bulk_delete(self, request):
        if request.method == 'POST':
            year = request.POST.get('year')
            specid = request.POST.get('specid')
            
            with connection.cursor() as cursor:
                if year and specid:
                    cursor.execute("DELETE FROM kpi.plans WHERE year = %s AND specid = %s", [year, specid])
                    messages.success(request, f'✅ Удалены планы за {year} год для специальности {specid}')
                elif year:
                    cursor.execute("DELETE FROM kpi.plans WHERE year = %s", [year])
                    messages.success(request, f'✅ Удалены все планы за {year} год')
                else:
                    messages.error(request, '❌ Укажите год для удаления')
            
            return redirect('..')
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT year FROM kpi.plans ORDER BY year DESC")
            years = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("SELECT keyidmis, text FROM kpi.specialities ORDER BY text")
            specializations = cursor.fetchall()
        
        return render(request, 'admin/plans_bulk_delete.html', {
            'title': 'Массовое удаление планов',
            'years': years,
            'specializations': specializations,
            'opts': self.model._meta,
        })

    # ===== КАСТОМНЫЙ ШАБЛОН =====
    change_list_template = 'admin/plans_changelist.html'