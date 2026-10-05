from django.contrib import admin
from django.urls import path

from game import views as game_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('assets/<path:path>', game_views.frontend_assets),
    path('', game_views.index),
]
