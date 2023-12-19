import logging
import urllib.parse
from typing import Any

from pyrus.models import entities as ent
from pyrus.models import responses as resp

from pyrustools.client_plus import MyPyrus
from pyrustools.object_methods import object_by_id
from pyrustools.objects_plus import TaskWithCommentsPlus, set_value_to_field

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3').propagate = False
logger = logging.getLogger(__name__)


def get_form_id_from_code(code: str) -> int:
    """

    Функиця для извлечения id формы из юкода таблицы.

    :param code: код из которого пытаемся извлечь id формы
    :return: id формы
    """
    lst_code = code.split('_')
    idx_report = lst_code.index('REPORT')
    try:
        str_form_id = lst_code[idx_report + 1]
        if not str_form_id.isdigit():
            return 0
        return int(str_form_id)
    except IndexError:
        return 0


def prepare_value(field: ent.FormField) -> str:
    """

    Приведение разных типов значений к строковому.

    :param field: поле, из которого извлекается значение
    :return: строковое значение
    """
    value = getattr(field, 'value', None)
    if value is None:
        value = 'Нет значения'
    if isinstance(value, ent.Person):
        if value.type == 'role':
            value = value.last_name
        else:
            value = f'{value.first_name} {value.last_name}'
    if isinstance(value, ent.MultipleChoice):
        value = value.choice_names[0]
    if isinstance(value, ent.CatalogItem):
        value = value.values[0]
    return str(value)


def prepare_registry_from_field(field: ent.FormField) -> str:
    """

    Подготовка куска ссылки для реестра в зависимости от поля и его значения.

    :param field: поле из значения которого формируется ссылка
    :return: строка ссылки
    """
    value = getattr(field, 'value', None)
    registry_dict = {}
    key = ''
    registry_value = ''
    if field.type == 'person':
        if value is None:
            registry_value = -1
        else:
            registry_value = value.id
        key = 'cid'
    if field.type == 'multiple_choice':
        if value is None:
            registry_value = 0
        else:
            registry_value = value.choice_id
        key = 'mch'
    if field.type == 'text':
        registry_value = value
        key = 'str'
        if value is None:
            registry_value = ''
    if field.type == 'catalog':
        if value is None:
            registry_value = ''
        else:
            registry_value = value.item_id
        key = 'ctf'
    if field.type == 'step':
        key = 'tst'
        registry_value = value
    if key:
        registry_dict[f'{key}{field.id}'] = registry_value
    registry_link = urllib.parse.urlencode(registry_dict)
    return registry_link


def prepare_registry_from_form(
        field: ent.FormField,
        value: str,
        client: MyPyrus
) -> (str, str):
    """

    Формирование ссылки реестра исходя из типа поля.

    и значения которое мы ищем в этом поле.

    :param field: поле из шаблона формы
    :param value: строковое значение
    :param client: сущность клиента пайрус
    :return: ключ для формирование реестра,
    значение для формирования реестра, привиденное к виду пайруса

    """
    key_reg, val_reg = '', ''
    field_type = field.type
    if field_type == 'text':
        val_reg = value
        key_reg = 'str'
    if field.type == 'multiple_choice':
        # Для поля выбор ищем в опциях id варианты выбора
        options_choice = getattr(field.info, 'options', [])
        my_options = [
            option.choice_id for option in options_choice
            if option.choice_value == value
        ]
        if my_options:
            val_reg = my_options[0]
            key_reg = 'mch'
        else:
            msg = f'Не удалось найти choice_id для {value} ' \
                  f'у поля c ID-NAME {field.id}-{field.name}'
            logger.debug(msg)
            return key_reg, val_reg
    if field.type == 'person':
        # Для типа контакт получаем все контакты организации
        # и ищем в ролях и в людях
        all_members = client.get_contacts()
        organizations = getattr(all_members, 'organizations', [])
        role = unit_from_organization(organizations, 'roles', value)
        person = unit_from_organization(organizations, 'persons', value)
        if role == -1 and person == -1:
            msg = f'Не найдено совпадений по контактам со значением {value}'
            logger.debug(msg)
            return key_reg, val_reg
        elif role != -1:
            val_reg = role
        elif person != -1:
            val_reg = person
        key_reg = 'cid'
    if field.type == 'catalog':
        # Для каталога получаем каталог и ищем по позиции
        # (по умолчанию 0, но может быть добавлена через запятую)
        catalog_id = getattr(field.info, 'catalog_id', 0)
        catalog = client.get_catalog(catalog_id)
        lst_value = value.split(',')
        [item.strip() for item in lst_value]
        if len(lst_value) == 1:
            lst_value.append('0')
        compare_value, pos = lst_value
        catalog_item_id = get_catalog_item(catalog, compare_value, pos)
        if catalog_item_id == -1:
            msg = f'Не найдено совпадений ' \
                  f'по каталогу {catalog_id} значения {value}'
            logger.debug(msg)
            return key_reg, val_reg
        val_reg = catalog_item_id
        key_reg = 'ctf'
    if field.type == 'checkmark':
        key_reg = 'chk'
        if value == 'checked':
            val_reg = 'true'
        else:
            val_reg = 'false'
    if field.type == 'step':
        key_reg = 'tst'
    return f'{key_reg}{field.id}', val_reg


def get_catalog_item(
        catalog: resp.CatalogResponse,
        compare_value: str,
        pos: str
) -> int:
    """

    Поиск в справочнике элемента по позиции и значению.

    :param catalog: сущность каталога
    :param compare_value: значение по которому ищется элемент каталога
    :param pos: позиция для поиска в справочнике
    :return: id элемента каталога
    """
    if not pos.isdigit():
        return -1
    pos = int(pos)
    for item in catalog.items:
        if item.values[pos] == compare_value:
            return item.item_id
    return -1


def unit_from_organization(
        orgs: [ent.Organization],
        unit: str,
        value: str
) -> int:
    """

    Поиск сущности в организации.

    :param orgs: список организаций в контакте
    :param unit: указание на то, где ищем (roles/persons)
    :param value: значение для поиска (название роли или имя и фамилия)
    :return: id контакта
    """
    for org in orgs:
        unit_values = getattr(org, unit, [])
        for unit_value in unit_values:
            if isinstance(unit_value, ent.Person):
                if value == f'{unit_value.first_name} {unit_value.last_name}':
                    return unit_value.id
            if isinstance(unit_value, ent.Role):
                if value == unit_value.name:
                    return unit_value.id
    return -1


def filter_tasks(
        tasks: [ent.Task],
        filtered_value: Any,
        filtered_field_id: int
) -> list:
    """

    Фильтрация задач по знаечению.

    :param tasks: список задач
    :param filtered_value: значение, по которому фильтруются задачи
    :param filtered_field_id: id поля по которому фильтруются задачи
    :return: список отфильтрованных задач
    """
    filtered_value = [elem.strip() for elem in filtered_value.split(',')]
    # Фильтрация задач по значению
    filtered_tasks = []
    for number in filtered_value:
        if '-' in number:
            start, end = [elem.strip() for elem in number.split('-')]
            filtered_tasks += [
                task for task in tasks
                if int(prepare_value(
                    object_by_id(task.flat_fields, filtered_field_id)
                )) in range(int(start), int(end) + 1)
            ]
        else:
            filtered_tasks += [
                task for task in tasks
                if number == prepare_value(
                    object_by_id(task.flat_fields, filtered_field_id)
                )
            ]
    return filtered_tasks


def get_rows(rows: [dict]) -> [ent.TableRow]:
    """

    Превращение списка словарей в значения строк таблицы.

    :param rows: список строк в виде словаря вида
     {id колонки: значение колонки}
    :return: список сущностей TableRow(готовые строки для вставки в таблицу)
    """
    rows_ent = []
    for idx, row in enumerate(rows):
        cells = [
            set_value_to_field(field_id, value)
            for field_id, value in row.items()
        ]
        row_ent = ent.TableRow(row_id=idx, cells=cells)
        rows_ent.append(row_ent)
    return rows_ent


def delete_table(
        client: MyPyrus,
        tables: dict,
        task: TaskWithCommentsPlus
) -> None:
    """

    Удаление текущих таблиц, которые будут обновлены.

    :param client: сущность клиента пайрус
    :param tables: словарь таблиц вида
     {id поля таблицы: новые значение этих таблиц}
    :param task: задача на которой происходит работа
    :return:
    """
    field_updates = []
    # Получаем таблицу из задачи, чтобы её очистить
    for table_id in tables.keys():
        table = object_by_id(task.flat_fields_static, table_id)
        table_value = getattr(table, 'value', None)
        rows = table_value if table_value else []
        for row in rows:
            row.delete = True
        table.value = rows
        field_updates.append(table)
    client.comment_task_plus(task.id, field_updates=field_updates)


def comment_tables(client: MyPyrus, tables: dict, task_id: int) -> None:
    """

    Запись новых данных в таблицы.

    :param client: сущность клиента пайрус
    :param tables: словарь таблиц вида
     {id поля таблицы: новые значение этих таблиц}
    :param task_id: id задачи, на которой происходит работа
    :return:

    """
    field_updates = [
        set_value_to_field(table_id, table)
        for table_id, table in tables.items()
    ]
    client.comment_task_plus(task_id, field_updates=field_updates)
