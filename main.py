from fastapi import FastAPI, Response, status

from config import DEV_TYPE, REDIS_URL, POSTGRES as pg

import aioredis
import random
import asyncpg


app = FastAPI()


@app.on_event("startup")
async def start():
    """Функция подключения к redis и к БД postgres"""
    global db_conn, redis
    db_conn = await asyncpg.connect(user=pg['user'], password=pg['password'], database=pg['database'], host=pg['host'],
                                     port=pg['port'])
    redis = aioredis.from_url(REDIS_URL)


@app.on_event("shutdown")
async def close_database():
    """Функция отключения от redis и от БД postgres"""
    await db_conn.close()
    await redis.close()


@app.get("/{first_word}/{second_word}/")
async def read_root(first_word: str, second_word: str):
    """
    Функция для проверки на принадлежность к анаграммам
    1. Принимает в url два слова, которые нужно проверить
    2. Проверяет их на принадлежность к анаграммам
    3. Возвращает данные в формате json счетчик redis и результат проверки
    """
    anagram = is_anagram(first_word, second_word)
    if anagram:
        a = await counter_up()
    else:
        a = await redis.get("counter")
    return {'counter': int(a), "anagram": anagram}


@app.get("/database_entry")
async def database_entry(response: Response):
    """Функция для внесения 10 записей в базу данных"""
    try:
        await insert_devices()
        ids_list = await get_last_ids()
        await insert_endpoints(ids_list)
        response.status_code = status.HTTP_201_CREATED
    except Exception as err:
        print(err)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


@app.get("/devices_by_category")
async def devices_by_category():
    """Функция для вывода количества устройств по типам, не входящих в таблицу endpoints"""
    try:
        devices_list = await select_devices()
        return devices_list
    except Exception as err:
        print(err)


async def counter_up():
    """Функция увеличения счетчика redis"""
    await redis.incr("counter")


def is_anagram(first_word, second_word):
    """Функция, проверяющая являются ли слова агаграммой"""
    first_word = sorted(first_word)
    second_word = sorted(second_word)
    if first_word == second_word:
        return True
    return False


def generate_mac():
    """Функция генерации случайных mac адресов"""
    mac = []
    for i in range(6):
        randstr = "".join(random.sample("0123456789abcdef", 2))
        mac.append(randstr)
    randmac = ":".join(mac)
    return randmac


def get_dev_type(dev_type):
    """Функция для получения типа устройства"""
    return dev_type[random.randint(0, 3)]


async def insert_devices():
    """Функция добавления 10 записей в таблицу devices"""
    for i in range(10):
        command = '''INSERT INTO devices (dev_id, dev_type) VALUES ($1, $2);'''
        values = [generate_mac(), get_dev_type(DEV_TYPE)]
        await db_conn.execute(command, *values)


async def get_last_ids():
    """Функция получения id последних 5 добавленных записей"""
    command = '''SELECT id FROM (SELECT * FROM devices ORDER BY id DESC LIMIT 5) t ORDER BY id'''
    data = await db_conn.fetch(command)
    ids_list = []
    for i in data:
        ids_list.append(i['id'])
    return ids_list


async def insert_endpoints(ids):
    """Функция добавления 5 записей в таблицу endpoints"""
    for i in ids:
        command = '''INSERT INTO endpoints (device_id) VALUES ($1);'''
        await db_conn.execute(command, i)


async def select_devices():
    """Функция выбора записей из таблицы devices, которых нет в таблице endpoints и группировка их по категории"""
    command = '''SELECT dev_type, COUNT(*) FROM devices LEFT OUTER JOIN endpoints ON devices.id = endpoints.device_id 
    WHERE endpoints.device_id is NULL GROUP BY devices.dev_type;'''
    devices_list = await db_conn.fetch(command)
    json_data = {}
    for i in devices_list:
        json_data[i['dev_type']] = i['count']
    return json_data
