#apps\references\admin.py
from django.contrib import admin
from .models import PerformanceGrade

@admin.register(PerformanceGrade)
class PerformanceGradeAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_percent', 'max_percent', 'points', 'color_preview', 'valid_from', 'valid_to', 'is_active_now']
    list_editable = ['min_percent', 'max_percent', 'points']
    list_filter = ['name', 'valid_from', 'valid_to']
    search_fields = ['name']
    ordering = ['min_percent']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'points')
        }),
        ('Процентный диапазон', {
            'fields': ('min_percent', 'max_percent'),
        }),
        ('Визуальное оформление', {
            'fields': ('color',),
        }),
        ('Период действия', {
            'fields': ('valid_from', 'valid_to'),
        }),
    )
    
    def color_preview(self, obj):
        """Отображает образец цвета в списке"""
        from django.utils.html import mark_safe
        return mark_safe(f'<span style="background-color: {obj.color}; padding: 2px 8px; border-radius: 4px; color: white;">{obj.color}</span>')
    color_preview.short_description = 'Цвет'
    
    def is_active_now(self, obj):
        """Показывает, активно ли правило на текущую дату"""
        from django.utils import timezone
        today = timezone.now().date()
        if obj.valid_from > today:
            return False
        if obj.valid_to and obj.valid_to < today:
            return False
        return True
    is_active_now.boolean = True
    is_active_now.short_description = 'Активно сейчас'
    
    def save_model(self, request, obj, form, change):
        """При сохранении проверяем пересечения диапазонов"""
        super().save_model(request, obj, form, change)