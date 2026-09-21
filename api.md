Order management
Get order events
Use this resource to return events that allow you to monitor actions which clients perform, i.e. making a purchase, filling in the checkout form (FOD), finishing payment process, making a surcharge. Read more: PL / EN.

Authorizations:
bearer-token-for-user
query Parameters
from	
string
You can use the event ID to retrieve subsequent chunks of events.

type	
Array of strings
Specify array of event types for filtering. Allowed values are:

BOUGHT: purchase without checkout form filled in
FILLED_IN: checkout form filled in but payment is not completed yet so data could still change
READY_FOR_PROCESSING: payment completed. Purchase is ready for processing
BUYER_CANCELLED: purchase was cancelled by buyer
FULFILLMENT_STATUS_CHANGED: fulfillment status changed
AUTO_CANCELLED: purchase was cancelled automatically by Allegro.
limit	
integer <int32> [ 1 .. 1000 ]
Default: 100
The maximum number of events returned in the response.

header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 OK
401 Unauthorized
403 Forbidden
422 Unprocessable Entity - Returned when query parameters are incorrect.

get
/order/events
Response samples
200
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"events": [
{}
]
}
Get order events statistics
Use this resource to returns object that contains event id and occurrence date of the latest event. It gives you current starting point for reading events. Read more: PL / EN.

Authorizations:
bearer-token-for-user
header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 OK
401 Unauthorized

get
/order/event-stats
Response samples
200
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"latestEvent": {
"id": "1532603898317497",
"occurredAt": "2018-10-12T10:12:32.321Z"
}
}
Get the user's orders
Use this resource to get an order list. Read more: PL / EN.

Authorizations:
bearer-token-for-user
query Parameters
offset	
integer >= 0
Default: 0
Index of first returned checkout-form from all search results.

limit	
integer [ 1 .. 100 ]
Default: 100
Maximum number of checkout-forms in response.

status	
string
Specify status value that checkout-forms must have to be included in the output. Allowed values are:

BOUGHT: purchase without checkout form filled in.
FILLED_IN: checkout form filled in but payment is not completed yet so data could still change.
READY_FOR_PROCESSING: payment completed. Purchase is ready for processing.
CANCELLED: purchase cancelled by buyer.
fulfillment.status	
string
Specify seller status value that checkout-forms must have to be included in the output. Allowed values are:

NEW
PROCESSING
READY_FOR_SHIPMENT
READY_FOR_PICKUP
SENT
PICKED_UP
CANCELLED
SUSPENDED
RETURNED.
fulfillment.provider.id	
string
Specify filter for order management provider. Allowed values are:

SELLER: for orders managed directly by seller
ALLEGRO: for orders managed by Allegro warehouse (One Fulfillment).
fulfillment.shipmentSummary.lineItemsSent	
string
Specify filter for line items sending status. Allowed values are:

NONE: none of line items have tracking number specified
SOME: some of line items have tracking number specified
ALL: all of line items have tracking number specified.
lineItems.boughtAt.lte	
string <date-time>
Latest line item bought date. The upper bound of date time range from which checkout forms will be taken.

lineItems.boughtAt.gte	
string <date-time>
Latest line item bought date. The lower bound of date time range from which checkout forms will be taken.

payment.id	
string
Find checkout-forms having specified payment id.

surcharges.id	
string
Find checkout-forms having specified surcharge id.

delivery.method.id	
string
Find checkout-forms having specified delivery method id.

buyer.login	
string
Find checkout-forms having specified buyer login.

marketplace.id	
string
Find checkout-forms of orders purchased on specified marketplace.

updatedAt.lte	
string <date-time>
Checkout form last modification date. The upper bound of date time range from which checkout forms will be taken.

updatedAt.gte	
string <date-time>
Checkout form last modification date. The lower bound of date time range from which checkout forms will be taken.

sort	
string
Enum: "lineItems.boughtAt" "-lineItems.boughtAt" "updatedAt" "-updatedAt"
The results' sorting order. No prefix in the value means ascending order. - prefix means descending order. If you don't provide the sort parameter, the list is sorted by line item boughtAt date, descending.

header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 OK
400 Bad Request - Returned when request parameters contains illegal values.
401 Unauthorized
406 Not Acceptable
422 Unprocessable Entity - Returned when limit or offset value is outside an acceptable range

get
/order/checkout-forms
Response samples
200
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"checkoutForms": [
{}
],
"count": 1,
"totalCount": 1
}
Get an order's details
Use this resource to get an order details. Read more: PL / EN.

Authorizations:
bearer-token-for-user
path Parameters
id
required
string <uuid>
Example: 29738e61-7f6a-11e8-ac45-09db60ede9d6
Checkout form identifier.

header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 OK
400 Bad Request
401 Unauthorized
404 Not Found
406 Not Acceptable
422 Unprocessable Entity - Returned when order id is malformed UUID.

get
/order/checkout-forms/{id}
Response samples
200
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"id": "29738e61-7f6a-11e8-ac45-09db60ede9d6",
"messageToSeller": "Please send me an item in red color",
"buyer": {
"id": "23123123",
"email": "user-email@allegro.pl",
"login": "User_Login",
"firstName": "Jan",
"lastName": "Kowalski",
"companyName": "Kowalex",
"guest": false,
"personalIdentity": "67062589524",
"phoneNumber": "123123123",
"preferences": {},
"address": {}
},
"payment": {
"id": "0f8f1d13-7e9e-11e8-9b00-c5b0dfb78ea6",
"type": "ONLINE",
"provider": "PAYU",
"finishedAt": "2018-10-12T10:12:32.321Z",
"paidAmount": {},
"reconciliation": {},
"features": []
},
"status": "READY_FOR_PROCESSING",
"fulfillment": {
"status": "SENT",
"shipmentSummary": {},
"provider": {}
},
"delivery": {
"address": {},
"method": {},
"pickupPoint": {},
"cost": {},
"time": {},
"smart": true,
"cancellation": {},
"calculatedNumberOfPackages": 1
},
"invoice": {
"required": true,
"address": {},
"dueDate": "2021-12-01",
"features": []
},
"lineItems": [
{}
],
"surcharges": [
{}
],
"note": {
"text": "Sample note"
},
"marketplace": {
"id": "allegro-pl"
},
"summary": {
"totalToPay": {}
},
"updatedAt": "2011-12-03T10:15:30.133Z",
"revision": "819b5836"
}
Get a list of available shipping carriers
Shipping carriers are essential to provide accurate tracking experience for customers. Use this resource to get a list of all available shipping carriers.

The response of this resource can be stored in accordance with returned caching headers. Read more: PL / EN.

Authorizations:
bearer-token-for-applicationbearer-token-for-user
header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 List of available shipping carriers.
401 Unauthorized
404 Not Found

get
/order/carriers
Response samples
200
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"carriers": [
{
"id": "POCZTA_POLSKA",
"name": "Poczta Polska"
},
{
"id": "DHL",
"name": "DHL"
},
{
"id": "YUN_EXPRESS",
"name": "Yun Express"
},
{
"id": "OTHER"
}
]
}
Get a list of parcel tracking numbers
Get a list of parcel tracking numbers currently assigned to the order. Orders can be retrieved using REST API resource GET /order/checkout-forms. Please note that the shipment list may contain parcel tracking numbers added through other channels such as Moje Allegro or by the carrier that delivers the parcel. Read more: PL / EN.

Authorizations:
bearer-token-for-user
path Parameters
id
required
string
Order identifier.

header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Responses
200 Returns a list of parcel tracking numbers (shipments)
401 Authentication failed, e.g. token is expired
404 Order not found or doesn’t belong to the seller

get
/order/checkout-forms/{id}/shipments
Response samples
200401404
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"shipments": [
{}
]
}
Add a parcel tracking number
Add a parcel tracking number (shipment) to given order line items. Read more: PL / EN.

Authorizations:
bearer-token-for-user
path Parameters
id
required
string
Order identifier.

header Parameters
Accept-Language	
string <BCP-47 language code>
Enum: "en-US" "pl-PL" "uk-UA" "sk-SK" "cs-CZ" "hu-HU"
Example: pl-PL
Expected language of messages.

Request Body schema: application/vnd.allegro.public.v1+json
request

carrierId
required
string
Supported carriers are available via shipping carriers resource.

waybill
required
string <= 64 characters
Waybill number (parcel tracking number). Cannot be empty and must be no longer than 64 characters.

carrierName	
string <= 30 characters
Carrier name to be provided only if carrierId is OTHER, otherwise it’s ignored. Must be no longer than 30 characters.

lineItems	
Array of objects
List of order line items. They must be from the order specified in the path parameter. When list is not provided or it is empty it means that every item from an order is included in shipment.

Responses
201 The request is OK and the parcel tracking number will be assigned to the order
400 Missing required field or invalid value in the request (e.g. unknown carrier id, carrier name too long, invalid tracking number structure)
401 Authentication failed, e.g. token is expired
404 Order not found or doesn’t belong to the seller
409 Maximum waybill usage exceeded (e.g. used in too many orders)
422 Some of the provided data is invalid, e.g. line item doesn’t belong to the order

post
/order/checkout-forms/{id}/shipments
Request samples
Payload
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"carrierId": "ALLEGRO",
"waybill": "AD-1239134",
"carrierName": "Sample carrier",
"lineItems": [
{}
]
}
Response samples
201400401404409422
Content type
application/vnd.allegro.public.v1+json

Copy
Expand allCollapse all
{
"id": "REhMOjEyMzQ1Njc4OTEwUEw=",
"waybill": "AD-1239134",
"carrierId": "ALLEGRO",
"carrierName": "Sample carrier",
"lineItems": [
{}
],
"createdAt": "2019-02-18T11:46:48.264Z"
}
