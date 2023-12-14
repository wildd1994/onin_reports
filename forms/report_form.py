import logging
import urllib.parse

from configuration_bot import BotConfig

from pyrus.models import entities as ent

from pyrustools.client_plus import MyPyrus
from pyrustools.object_methods import (get_id_by_code, object_by_code,
                                       object_by_id)
from pyrustools.objects_plus import FormFieldPlus, TaskWithCommentsPlus

import utils


logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3').propagate = False
logger = logging.getLogger(__name__)


def process_reports(
        client: MyPyrus,
        config: BotConfig,
        task: TaskWithCommentsPlus
) -> None:
    """

    Обработка кросс-таблиц.

    :param client: сущность клиента pyrus
    :param config: конфигурационный файл
    :param task: задача на которой работаем
    :return:
    """
    # Получаем поля шаблона формы
    form_fields = task.form_template.flat_fields_static
    res = {}
    # Получаем дополнительные фильтры для таблиц
    filters = get_additional_filters(
        task.flat_fields_static,
        config.filters_code
    )
    filters_to_id = {}
    # Ищем таблицы для отчетов
    for field in form_fields:
        type_field = getattr(field, 'type', None)
        code_field = getattr(field.info, 'code', None)
        if code_field is None:
            continue
        if type_field == 'table' and 'REPORT' in code_field:
            report_form_id = utils.get_form_id_from_code(code_field)
            if report_form_id is None:
                continue
            res[field] = report_form_id
            filter_table = filters.get(code_field)
            if filter_table:
                filters_to_id[field.id] = filter_table
    # Получаем id поля, по которому будем сортировать
    # Получаем новые таблицы
    new_tables = get_tables(res, client, config, filters_to_id)
    if not new_tables:
        client.comment_task_plus(
            task_id=task.id,
            text='Сортировать можно только числа! Поправьте конфигурацию'
        )
        return
    # Переписываем таблицы
    rewrite_tables(client, new_tables, task)


def rewrite_tables(
        client: MyPyrus,
        tables: dict,
        task: TaskWithCommentsPlus
) -> None:
    """

    Перезапись таблиц.

    :param client: сущность клиента pyrus
    :param tables: новые таблиы для записи
    :param task: задача, на которой происходит работа
    :return:
    """
    # Удаляем старые таблицы
    utils.delete_table(client, tables, task)
    # Пишем новые таблицы
    utils.comment_tables(client, tables, task.id)


def forming_columns_for_sort(columns: list[FormFieldPlus]) -> (list, list):
    """
    Функция формирует структуру для дальнейшей правильной сортировки

    :param columns: список обьектов колонок
    :return:
        u_code_columns_list: список словарей с ключами {'u_code', 'id', 'name'}
         для 'оригинальных' колонок, чтобы избежать зануления текущих колонок
        sorted_fields: список словарей с ключами {'id', 'number', 'reverse'}
         полей сортировки
    """
    u_code_columns_list = []
    sorted_fields = []
    for col in columns:
        code = getattr(col.info, 'code', None)  # Весь юкод
        code_split = code.split('$')
        code_name = code_split[0]  # До доллара
        if len(code_split) == 2:
            (code_sign, code_number,
             code_revers) = code_split[1].split('_')  # Сплитим после $
            if code_sign == 'SRT':
                sorted_fields.append(
                    {
                        'number': code_number,
                        'id': getattr(col, 'id', None),
                        'reverse': True if code_revers == 'DESC' else False
                    }
                )
        u_code_columns_list.append(  # Переделал чтобы не занулялись поля
            {
                'u_code': code_name,
                'id': getattr(col, 'id', None),
                'name': getattr(col, 'name', None)
            }
        )
    sorted_fields.sort(key=lambda x: int(x['number']))
    return u_code_columns_list, sorted_fields


def get_tables(
        field_table_to_form_id: dict,
        client: MyPyrus,
        config: BotConfig,
        filters: dict
) -> (dict, None):
    """

    Получение таблиц для записи.

    :param field_table_to_form_id: словарь вида
     {поле таблицы: id формы с которой собирается для нее отчет}
    :param client: сущность клиента pyrus
    :param config: конфигурационный файл
    :param filters: дополнительные фильтры для таблиц
    :return: словарь таблиц вида {id таблицы: строки для записи в неё}, None
    """
    cache = {}
    tables = {}
    # Для каждой таблицы получаем поля формы и реестр формы
    for table, form_id in field_table_to_form_id.items():
        # Сохраняем их в кэш, чтобы не брать одну и ту же форму несколько раз
        if form_id in cache:
            cash_form_meta = cache.get(form_id)
            form = cash_form_meta[0]
            registry_form = cash_form_meta[1]
        else:
            form = client.get_form(form_id)
            registry_form = client.get_registry(form_id)
            cache[form_id] = [form, registry_form]
        # Получаем задачи реестра
        tasks = registry_form.tasks if registry_form.tasks is not None else []
        filter_to_table = filters.get(table.id)
        registry_part = ''
        # Фильтруем по данным из фильтрационной таблицы
        if filter_to_table:
            tasks, registry_part = to_filter_add(
                form.flat_fields_static,
                tasks,
                filter_to_table,
                client
            )
        columns = getattr(table.info, 'columns', [])
        u_code_columns_list, sorted_fields = forming_columns_for_sort(columns)
        for coll in sorted_fields:
            if object_by_id(columns, coll['id']).type != 'number':
                logger.debug(msg='Сортировать можно только числа!')
                return
        # Обрабатываем первый столбец
        rows, filtered_tasks = prepare_first_col(
            u_code_columns_list[0],
            form.flat_fields_static,
            tasks,
            config
        )
        # Обрабатываем остальные столбцы
        prepare_other_col(
            u_code_columns_list[1::],
            form.flat_fields_static,
            rows,
            filtered_tasks,
            config,
            form_id,
            registry_part
        )
        # Формируем строки
        if sorted_fields:
            sort_table(rows, sorted_fields)
        rows_ent = utils.get_rows(rows)
        tables[table.id] = rows_ent
    return tables


def prepare_first_col(
        first_col: dict,
        source_form_fields: [FormFieldPlus],
        tasks: [ent.Task],
        config: BotConfig
) -> (list, dict):
    """

    Обработка первого столбца.

    :param first_col: первый столбец таблицы в виде словаря
     (словарь с ключами {'u_code', 'id', 'name'})
    :param source_form_fields: список полей формы
    :param tasks: список задач из реестра
    :param config: конфигурационный файл
    :return: список строк, отсортированные задачи по значению колонки
    """
    res = {}
    rows = []
    # Получаем юкод из столбца,
    # значение которого будем раскладывать в вертикаль
    code_source = first_col.get('u_code', None)
    if code_source in config.mapping_service_code:
        code_source = config.mapping_service_code.get(code_source)
    first_col_id = first_col.get('id', None)
    if code_source is None:
        return rows, res
    # Получаем id поля по юкоду из столбца
    source_field_id = get_id_by_code(source_form_fields, code_source)
    for task in tasks:
        # Получаем значение этого поля для каждой задачи
        first_value_field = object_by_id(task.flat_fields, source_field_id)
        value = utils.prepare_value(first_value_field)
        # Получаем кусок ссылки на реестр
        registry_link = utils.prepare_registry_from_field(first_value_field)
        # Собираем в ключ вида (значение поля, ссылка на реестр)
        composite_value = (value, registry_link)
        # Фильтруем задачи по значению поля
        if composite_value in res:
            res[composite_value].append(task)
        else:
            res[composite_value] = [task]
            rows.append({first_col_id: value})
    # Добавляем итоговую служебную строку
    res[('Всего', '')] = tasks
    rows.append({first_col_id: 'Всего'})
    return rows, res


def prepare_other_col(
        columns: list,
        source_form_fields: list,
        rows: list,
        tasks_by_item: dict,
        config: BotConfig,
        form_id: int,
        filter_registry_link: str
) -> None:
    """

    Обработка дефолтных столбцов.

    :param columns: список словарей колонок
    (словарь с ключами {'u_code', 'id', 'name'})
    :param source_form_fields: список полей формы
    :param rows: строки для будущей таблицы
    :param tasks_by_item: отсортированные задачи
    :param config: конфигурационный файл
    :param form_id: id формы
    :param filter_registry_link: ссылка на реестр
    :return:
    """
    # Остальные колонки присоединяем к строкам,
    # которые им соответствуют (в том порядке, в котором они идут)
    for col in columns:
        code_source = col.get('u_code', None)
        # Если служебный код, меняем его
        if code_source in config.mapping_service_code:
            code_source = config.mapping_service_code.get(code_source)
        source_field_id = get_id_by_code(source_form_fields, code_source)
        source_value_for_common = col.get('name', None)
        i = 0
        for meta, tasks in tasks_by_item.items():
            # Служебная итоговая колонка
            if code_source == config.total_code:
                value = len(tasks)
            # Служебная колонка для реестра
            elif code_source == config.registry_code:
                value = f'https://pyrus.com/t#rg{form_id}?ao=true&tz=180&sm=0'
                if meta[1]:
                    value = f'{value}&{meta[1]}'
                if filter_registry_link:
                    value = f'{value}&{filter_registry_link}'
            # Остальные колонки
            else:
                value = len(
                    utils.filter_tasks(
                        tasks, source_value_for_common, source_field_id
                    )
                )
            rows[i][col['id']] = value
            i += 1


def get_additional_filters(
        task_fields: [FormFieldPlus],
        code_add_filter: str
) -> dict:
    """

    Получаем фильтры из таблицы.

    :param task_fields: список полей задачи
    :param code_add_filter: код таблицы с фильтрами
    :return: словарь вида {юкод таблицы на которую применяются фильтры:
     список списков фильтров вида
    [[юкод фильтруемого поля, значение фильтруемого поля]]}
    """
    filters = {}
    # Получаем таблицу с фильтрами
    table_with_filters = object_by_code(task_fields, code_add_filter)
    value_table = getattr(table_with_filters, 'value', None)
    rows = value_table if value_table else []
    for row in rows:
        # получаем данные для фильтрации
        filtered_table = getattr(
            object_by_code(row.cells, 'filter_table'), 'value'
        )
        filter_field_code = getattr(
            object_by_code(row.cells, 'filter_field'), 'value'
        )
        filter_value = getattr(
            object_by_code(row.cells, 'filter_value'), 'value'
        )
        # добавляем к фильтрам
        if filtered_table in filters:
            filters[filtered_table].append([filter_field_code, filter_value])
        else:
            filters[filtered_table] = [[filter_field_code, filter_value]]
    return filters


def to_filter_add(
        form_fields: [FormFieldPlus],
        tasks: [ent.Task],
        filters_data: [[]],
        client: MyPyrus
) -> (list, str):
    """

    Накладываем дополнительные фильтры полученные ранее.

    :param form_fields: список полей шаблона формы
    :param tasks: список задач из реестра
    :param filters_data: список списков фильтров вида
    [[юкод фильтруемого поля, значение фильтруемого поля]]
    :param client: сущность клиента pyrus
    :return: список отфильтрованных задач, ссылку на реестр
    """
    registry_dict = {}
    for filter_data in filters_data:
        # получаем код
        filter_field_code = filter_data[0]
        # получаем значение
        filter_value = filter_data[1]
        # Получаем поле из шаблона форма
        filter_field = object_by_code(form_fields, filter_field_code)
        # фильтруем задачи
        tasks = utils.filter_tasks(tasks, filter_value, filter_field.id)
        # получаем ссылку на реестр
        key_registry, value_registry = utils.prepare_registry_from_form(
            filter_field,
            filter_value,
            client
        )
        if key_registry:
            registry_dict[key_registry] = value_registry
    # формируем ссылку
    registry_link = urllib.parse.urlencode(registry_dict)
    return tasks, registry_link


def sort_table(rows: list, fields: list) -> None:
    """

    Сортировка таблиц по полю итого.

    :param rows: строки которые надо отсортировать
    :param fields список словарей с ключами {'id', 'number', 'reverse'}
    полей по которым сортируются строки
    :return: None модифицируем исходный массив
    """
    last_row = rows.pop(-1)
    sort_ids_list = [
        -cell['id'] if cell['reverse'] else cell['id'] for cell in fields
    ]
    rows.sort(
        key=lambda item: [item.get(idd) if idd > 0 else -item.get(abs(idd))
                          for idd in sort_ids_list]
    )
    rows.append(last_row)
