# apps/users/models.py

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

class Role(models.Model):
    """Модель для ролей пользователей"""
    keyid = models.AutoField(primary_key=True)
    text = models.CharField(max_length=100, unique=True, verbose_name='Название роли')
    status = models.BooleanField(default=True, verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        managed = False  # Таблица управляется PostgreSQL
        db_table = 'kpi"."roles'
        app_label = 'users'
        verbose_name = 'Роль'
        verbose_name_plural = 'Роли'

    def __str__(self):
        return self.text
    
class UserManager(BaseUserManager):
    def create_user(self, login, password=None, **extra_fields):
        if not login:
            raise ValueError('The Login must be set')
        
        user = self.model(login=login, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('status', True)
        
        return self.create_user(login, password, **extra_fields)
    
class User(AbstractBaseUser):
    """Модель пользователя"""
    keyid = models.AutoField(primary_key=True)
    login = models.CharField(max_length=200, unique=True, verbose_name='Логин')
    password = models.CharField(max_length=128, verbose_name='Пароль')
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, 
                             db_column='role_id', verbose_name='Роль')
    manid = models.IntegerField(null=True, blank=True, verbose_name='ID из МИС (man)')
    status = models.BooleanField(default=True, verbose_name='Статус')
    is_superuser = models.BooleanField(default=False, verbose_name='Суперпользователь')
    last_login = models.DateTimeField(null=True, blank=True, verbose_name='Последний вход')
    date_joined = models.DateTimeField(default=timezone.now, verbose_name='Дата регистрации')
    
    objects = UserManager()
    
    USERNAME_FIELD = 'login'
    REQUIRED_FIELDS = []

    class Meta:
        managed = False  # Таблица управляется PostgreSQL
        db_table = 'kpi"."users'
        app_label = 'users'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.login

    def set_password(self, raw_password):
        """Шифруем пароль при сохранении"""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Проверяем пароль"""
        return check_password(raw_password, self.password)

    @property
    def is_staff(self):
        """Определяем, является ли пользователь персоналом"""
        return self.is_superuser or (self.role and self.role.text == 'Администратор')

    def is_accountant(self):
        return self.role and self.role.text == 'Заведующий'

    def is_doctor(self):
        return self.role and self.role.text == 'Врач'
    
    def get_full_name(self):
        # Пытаемся получить имя из таблицы man по manid
        if self.manid:
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT text FROM solution_med.import_man WHERE manidmis = %s",
                        [self.manid]
                    )
                    result = cursor.fetchone()
                    if result:
                        return result[0]
            except:
                pass
        return self.login
    
    def get_short_name(self):
        return self.login

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser