from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Persisted player profile/settings, replacing steer/main.py's ~/.steer_profile.json.

    Field set mirrors load_profile()'s defaults in main.py. Settings views/forms to actually
    read & write this from the frontend are the next increment -- this is the data layer.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    name = models.CharField(max_length=12, default="Player")
    flag = models.CharField(max_length=8, default="us")
    races = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    best_lap = models.FloatField(default=0.0)

    master_volume = models.FloatField(default=1.0)
    sfx_volume = models.FloatField(default=0.8)
    music_volume = models.FloatField(default=0.6)

    laps = models.PositiveSmallIntegerField(default=3)
    steer_rate = models.FloatField(default=1.0)
    invert_steer = models.BooleanField(default=False)
    bot_aggression = models.CharField(max_length=16, default="Casual")
    track_type = models.CharField(max_length=32, default="meadow_dirt")

    # free-form bucket for settings not yet promoted to a real column (shaders, keybinds, ...)
    extra = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Profile({self.user.username})"
