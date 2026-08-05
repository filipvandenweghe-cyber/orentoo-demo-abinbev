from . import models
from . import services


def post_init_hook(env):
    """Schedule the weather cron immediately after installation."""
    env['res.config.settings']._update_weather_cron_schedule()
