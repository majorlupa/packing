/shipment-management/delivery-services:
    get:
      tags:
        - Shipment management
      summary: Get available delivery services
      description: >-
        Use this resource to get delivery services available for user. It returns services provided by Allegro and contracts with carriers owned by user and configured by GUI. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-pobrac-liste-uslug-dostawy" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-retrieve-a-list-of-delivery-services" target="_blank">EN</a>.
      operationId: getDeliveryServices
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/DeliveryServicesDto
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/shipments/create-commands:
    post:
      tags:
        - Shipment management
      summary: Create new shipment
      description:
        'Use this resource to create shipment for delivery. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-utworzyc-nowa-paczke" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-create-a-new-shipment" target="_blank">EN</a>.'
      operationId: createNewShipment
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/ShipmentCreateCommandDto
        required: true
      responses:
        '200':
          description: OK
          headers:
            Retry-After:
              schema:
                type: integer
                minimum: 1
              description: Suggested time interval (in seconds) between follow-up command status queries.
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/ShipmentCreateCommandDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/shipments/create-commands/{commandId}:
    get:
      tags:
        - Shipment management
      summary: Get shipment creation command status
      description:
        'Use this resource to get shipment creation status. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-sprawdzic-status-utworzenia-paczki" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-check-the-creation-status-of-a-shipment" target="_blank">EN</a>.'
      operationId: getShipmentCreationStatus
      parameters:
        - name: commandId
          in: path
          required: true
          schema:
            type: string
          example: 14e142cf-e8e0-48cc-bcf6-399b5fd90b32
          description: Command UUID.
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/CreateShipmentCommandStatusDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Not Found
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/shipments/cancel-commands:
    post:
      tags:
        - Shipment management
      summary: Cancel shipment
      description: 'Use this resource to cancel parcel. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-anulowac-paczke" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-cancel-a-shipment" target="_blank">EN</a>.'
      operationId: cancelShipment
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/ShipmentCancelCommandDto
        required: true
      responses:
        '200':
          description: OK
          headers:
            Retry-After:
              schema:
                type: integer
                minimum: 1
              description: Suggested time interval (in seconds) between follow-up command status queries.
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/ShipmentCancelCommandDto
        '400':
          description: Bad request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/shipments/cancel-commands/{commandId}:
    get:
      tags:
        - Shipment management
      summary: Get shipment cancellation status
      description: 'Use this resource to get parcel cancellation status. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-sprawdzic-status-anulowania-paczki" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-check-shipment-cancellation-status" target="_blank">EN</a>.'
      operationId: getShipmentCancellationStatus
      parameters:
        - name: commandId
          in: path
          required: true
          schema:
            type: string
          example: 14e142cf-e8e0-48cc-bcf6-399b5fd90b32
          description: Command UUID.
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          headers:
            Retry-After:
              schema:
                type: integer
                minimum: 1
              description: Suggested time interval (in seconds) between follow-up command status queries.
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/CancelShipmentCommandStatusDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Not Found
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/shipments/{shipmentId}:
    get:
      tags:
        - Shipment management
      summary: Get shipment details
      description: 'Use this resource to get parcel details. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-pobrac-szczegolowe-informacje-o-paczce" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-retrieve-shipment-details" target="_blank">EN</a>.'
      operationId: getShipmentDetails
      parameters:
        - name: shipmentId
          in: path
          required: true
          description: Shipment id.
          schema:
            type: string
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/ShipmentDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Not Found
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error404'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:read
  /shipment-management/label:
    post:
      tags:
        - Shipment management
      summary: Get shipments labels
      description: >-
        Use this resource to get label for created shipment.
        <br/>Returned content type depends on created shipment. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-utworzyc-etykiete-na-paczke" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-create-a-label-for-shipment" target="_blank">EN</a>.
      operationId: getShipmentLabels
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/LabelRequestDto
        required: true
      responses:
        '200':
          description: OK
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
                description: File in a binary format
        '204':
          description: No Label For Given Parcel
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Shipment Not Found
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error404'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:read
  /shipment-management/protocol:
    post:
      tags:
        - Shipment management
      summary: Get shipments protocol
      description: >-
        Protocol availability depends on Carrier.
        Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-pobrac-protokol-nadania-przesylek" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-retrieve-shipment-protocol" target="_blank">EN</a>.
      operationId: getShipmentProtocol
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/ShipmentIdsDto
        required: true
      responses:
        '200':
          description: OK
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
                description: File in a binary format
        '204':
          description: No Protocol For Given Parcels
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Shipment Not Found
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error404'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:read
  /shipment-management/pickup-proposals:
    post:
      tags:
        - Shipment management
      summary: Get shipments pickup proposals
      description: >-
        Use this resource to get parcels pickup date proposals. Pickup takes place, when courier arrives to take parcels for shipment. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-sprawdzic-proponowana-date-odbioru-paczek-przez-kuriera" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-check-pickup-date-proposals" target="_blank">EN</a>.
      operationId: getPickupProposals
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/PickupProposalsRequestDto
        required: true
      responses:
        '200':
          description: OK
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                type: array
                items:
                  $ref: >-
                    #/components/schemas/PickupProposalsResponseDto
        '400':
          description: Bad request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/pickups/create-commands:
    post:
      tags:
        - Shipment management
      summary: Request shipments pickup
      description: 'Use this resource to request a pickup of shipments. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-zamowic-odbior-paczek-przez-kuriera" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-request-shipment-pickup-by-a-courier" target="_blank">EN</a>.'
      operationId: createPickup
      parameters:
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      requestBody:
        content:
          application/vnd.allegro.public.v1+json:
            schema:
              $ref: >-
                #/components/schemas/PickupCreateCommandDto
        required: true
      responses:
        '200':
          description: OK
          headers:
            Retry-After:
              schema:
                type: integer
                minimum: 1
              description: Suggested time interval (in seconds) between follow-up command status queries.
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/PickupCreateCommandDto
        '400':
          description: Bad request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/pickups/create-commands/{commandId}:
    get:
      tags:
        - Shipment management
      summary: Create pickup command status
      description: 'Use this resource to get pickup request status. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-sprawdzic-status-zamowienia-odbioru-paczek" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-check-shipment-pickup-request-status" target="_blank">EN</a>.'
      operationId: createPickupStatus
      parameters:
        - name: commandId
          in: path
          required: true
          example: 14e142cf-e8e0-48cc-bcf6-399b5fd90b32
          description: Command UUID.
          schema:
            type: string
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          headers:
            Retry-After:
              schema:
                type: integer
                minimum: 1
              description: Suggested time interval (in seconds) between follow-up command status queries.
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/CreatePickupCommandStatusDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Not Found
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:write
  /shipment-management/pickups/{pickupId}:
    get:
      tags:
        - Shipment management
      summary: Get pickup details
      description: 'Use this resource to get pickup details. Read more: <a href="../../tutorials/jak-zarzadzac-przesylkami-przez-wysylam-z-allegro-LRVjK7K21sY#jak-sprawdzic-status-zamowienia-odbioru-paczek" target="_blank">PL</a> / <a href="../../tutorials/how-to-manage-parcels-via-ship-with-allegro-ZM9YAyGKWTV#how-to-check-shipment-pickup-request-status" target="_blank">EN</a>.'
      operationId: getPickupDetails
      parameters:
        - name: pickupId
          in: path
          required: true
          description: Pickup ID.
          schema:
            type: string
        - name: Accept-Language
          in: header
          required: false
          description: Expected language of messages.
          example: en-US
          schema:
            type: string
            format: BCP-47 language code
            enum:
              - en-US
              - pl-PL
              - uk-UA
              - sk-SK
              - cs-CZ
              - hu-HU
      responses:
        '200':
          description: OK
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: >-
                  #/components/schemas/PickupDto
        '400':
          description: Bad Request
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error400'
        '401':
          description: Unauthorized
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                $ref: '#/components/schemas/AuthError'
        '403':
          description: Forbidden
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error403'
        '404':
          description: Not Found
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error404'
        '504':
          description: Gateway Timeout
          content:
            application/vnd.allegro.public.v1+json:
              schema:
                properties:
                  errors:
                    type: array
                    description: Array of errors.
                    items:
                      $ref: '#/components/schemas/Error504'
      security:
        - bearer-token-for-user:
            - allegro:api:shipments:read
