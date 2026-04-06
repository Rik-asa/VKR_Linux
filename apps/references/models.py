# apps/references/models.py

from django.db import models

class Specialization(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class PlanType(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    formula_hint = models.TextField(blank=True)

    def __str__(self):
        return self.name

class PerformanceGrade(models.Model):
    """Правила оценки процентов выполнения (цвета, баллы)"""
    name = models.CharField(max_length=100, verbose_name='Название')
    min_percent = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Мин. процент')
    max_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Макс. процент')
    points = models.IntegerField(default=0, verbose_name='Баллы')
    color = models.CharField(max_length=7, verbose_name='HEX-код цвета')
    valid_from = models.DateField(verbose_name='Действует с')
    valid_to = models.DateField(null=True, blank=True, verbose_name='Действует по')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        managed = False  # Таблица уже существует в БД
        db_table = 'kpi"."performance_grades'
        ordering = ['min_percent']
        verbose_name = 'Правило оценки'
        verbose_name_plural = 'Правила оценки'

    def __str__(self):
        if self.max_percent is None:
            return f"{self.name} (от {self.min_percent}% и выше) — {self.points} баллов"
        else:
            return f"{self.name} ({self.min_percent}%-{self.max_percent}%) — {self.points} баллов"

    def get_color_style(self):
        """Возвращает CSS стиль для цвета"""
        return f'color: {self.color}; font-weight: bold;'