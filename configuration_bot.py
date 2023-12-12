class BotConfig:
    """Конфигурационный файл приложения."""

    def __init__(self, config):
        self.allow_form_ids = config.get('ALLOW_FORMS', [])
        self.mapping_service_code = config.get('MAPPING_FOR_SERVICE_FIELD', {})
        self.total_code = config.get('TOTAL_CODE')
        self.registry_code = config.get('REGISTRY_CODE')
        self.filters_code = config.get('CODE_ADDITIONAL_FILTERS')
