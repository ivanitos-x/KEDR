from .redaction import redact

ERRORS = {
    'CLAP-RENDER-009': 'Не удалось прочитать HDRI; выберите корректный Radiance RGBE файл',
    'CLAP-RENDER-005': 'Неподдерживаемая возможность файла',
    'CLAP-RENDER-006': 'Необходимый обработчик или библиотека недоступны',
    'CLAP-RENDER-007': 'Загрузка отменена',
    'CLAP-RENDER-008': 'Истёк бюджет времени загрузки',
    'CLAP-RENDER-001': 'Не удалось прочитать геометрию модели; проверьте формат и целостность файла',
    'CLAP-RENDER-002': 'Графическое устройство недоступно; обновите драйвер',
    'CLAP-RENDER-003': 'Ошибка прозрачного рендеринга; проверьте поддержку OpenGL',
    'CLAP-RENDER-004': 'Превышен лимит ресурсов; уменьшите модель',
    'CLAP-FILE-001': 'Файл недоступен или превышает лимит',
    'CLAP-FILE-002': 'Ожидается текст UTF-8',
    'CLAP-JSON-001': 'Некорректный JSON',
    'CLAP-QUEUE-001': 'Задание не прошло проверку импортёра CLAP',
    'CLAP-QUEUE-002': 'Не удалось атомарно добавить задания',
    'CLAP-SEC-001': 'Доступ к ресурсу документа запрещён',
    'CLAP-VIEW-001': 'Неподдерживаемый или повреждённый документ',
    'CLAP-VIEW-002': 'Не удалось открыть PNG',
    'CLAP-INTEGRATION-001': 'Платформа CLAP недоступна',
}

class ViewerError(Exception):
    def __init__(self, code, detail='', *, file='', line=None, column=None, task='', field=''):
        self.code, self.file, self.line, self.column = code, str(file), line, column
        self.task, self.field = task, field
        self.detail = redact(detail)
        super().__init__(self.format())

    def format(self):
        location = f'{self.file}'
        if self.line is not None:
            location += f':{self.line}:{self.column}'
        return f'{self.code}: {ERRORS[self.code]}\n{location}\nID: {self.task}; поле: {self.field}\n{self.detail}\nПроверьте файл и повторите действие.'
