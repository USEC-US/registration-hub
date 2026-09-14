VietQR, is an open and required for banks supporting QR Code Payment, QR Code specification for Viet Nam banks, allowing individuals, merchants, and businesses to make transactions and payment quickly and more conveient.

Unlike VNPAY, however, where it's almost propriatary and licensed to the State Bank of Vietnam in 2011, VietQR comes out later in 2021 and is the national standard from [NAPAS (National Payment Corporation of Vietnam)](https://en.napas.com.vn/napas-for-a-cashless-society), with the SBV being its one of the main shareholder. Both follows the same [EMVCo's QR Code Specification](https://www.emvco.com/emv-technologies/qr-codes/).

Note: [`vietqr.net`](https://vietqr.net) is the actual site ran by NAPAS. Other domains related to VietQR are 3rd party services and not related to the official VietQR project.

- The full specification is [here](./QR_Format_T&C_v1.5.2_EN_102022.pdf).
- Available Bank Identification Numbers are published here: <https://sbv.gov.vn/vi/w/cnthwebap01162394697>
- A public API for the BINs (is it updated?) is here: <https://sandbox.bankhub.dev/fi-services>. API Schema: <https://vietqr.io/danh-sach-api/api-danh-sach-ma-ngan-hang>
- VietQR Code Generation example, detailed writeup, and other helpful utils (Go): <https://github.com/subiz/vietqr/blob/master/README.md>

Since it's an open format, we can just make our own util function to generate the VietQR transfer code.