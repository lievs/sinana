# Обмен SINANA с 1С

Все запросы выполняются по HTTPS с заголовком `X-API-Key`, значение которого совпадает с `SINANA_1C_API_TOKEN` на сервере. Повторная загрузка безопасна: товары находятся по штрихкоду, заказы — по номеру SINANA и идентификатору 1С.

## Номенклатура из выбранной группы

В настройках SINANA указывается GUID группы 1С. Обработка отправляет только эту группу на `POST /api/1c/catalog`:

```json
{
  "group_id": "GUID-группы",
  "full_sync": true,
  "items": [
    {
      "external_id": "GUID-товара",
      "barcode": "460001",
      "name": "Торт шоколадный",
      "type": "finished",
      "unit": "шт",
      "shelf_life_days": 5,
      "allergens": "молоко, глютен",
      "cost": 410.50,
      "price": 900.00
    }
  ]
}
```

Типы товара: `raw`, `semi_finished`, `finished`, `packaging`.

## Контрагенты и склады

- `POST /api/1c/counterparties` — реквизиты, контакты, задолженность и отсрочка в поле `payment_terms_days`.
- `POST /api/1c/warehouses` — склады из 1С.
- `POST /api/1c/prices` — типы цен и цены товаров. В контрагенте поле `price_type_external_id` связывает его с нужным типом.

## Остатки и цены из 1С

`POST /api/1c/stocks`

```json
{
  "items": [
    {"barcode": "460001", "warehouse_external_id": "GUID-склада", "quantity": 125, "price": 390.00}
  ]
}
```

## Получение заказов в 1С

`GET /api/1c/orders?unsynced=1`

Ответ содержит клиента, торгового представителя и строки заказа. Пока 1С не подтвердит заказ, он будет возвращаться снова — это защищает от потери при обрыве соединения.

## Подтверждение заказа и обновление статуса

`POST /api/1c/orders/ack`

```json
{
  "orders": [
    {
      "number": "SIN-20260926-ABC123",
      "external_id": "e1cib-guid",
      "external_number": "ЗК-000015",
      "status": "confirmed"
    }
  ]
}
```

Допустимые статусы: `submitted`, `confirmed`, `assembled`, `delivered`, `paid`, `cancelled`. Последующие изменения статуса отправляются тем же форматом на `/api/1c/orders/statuses`.

## Проверка соединения

`GET /api/1c/health`

## Возвраты

1С получает проведённые возвраты через `GET /api/1c/returns` и подтверждает их вызовом `POST /api/1c/returns/ack`. До подтверждения один документ может выдаваться повторно, поэтому обработка должна искать его по полю `number`, а не создавать дубль.
