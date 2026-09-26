"""天气数据源（校准健身房外部事实层）。"""

from .provider import DayWeather, ClimoStats, OpenMeteoProvider, WeatherProviderError

__all__ = ["DayWeather", "ClimoStats", "OpenMeteoProvider", "WeatherProviderError"]
