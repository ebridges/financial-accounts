# Matching Patterns

These are the set of payee description lines from imported transactions that the regexes in `matching-config.json` are based on.

## From 1381 -> 6039

```
CHASE CREDIT CRD AUTOPAY                    PPD ID: xxxxxxxxxx
CHASE CREDIT CRD AUTOPAY PPD ID: xxxxxxxxxx
CHASE CREDIT CRD AUTOPAY xxxxxxxxxxxxxxx PPD ID: xxxxxxxxxx
CITI AUTOPAY     PAYMENT    xxxxxxxxxxxxxxx WEB ID: CITICARDAP
Payment to Chase card ending in xxxx xx/xx
```

## From 1381 -> 1605

```
Online Transfer from CHK ...1605
Online Transfer from CHK ...1605 transaction#: xxxxxxxxxx
Online Transfer from CHK ...1605 transaction#: xxxxxxxxxxx
Online Transfer to  CHK ...1605
Online Transfer to  CHK ...1605 transaction#: xxxxxxxxxxx xx/xx
Online Transfer to CHK ...1605 t
Online Transfer to CHK ...1605 transaction#: xx/xx
Online Transfer to CHK ...1605 transaction#: xxxxxxxxxx xx/xx
Online Transfer to CHK ...1605 transaction#: xxxxxxxxxxx xx/xx
```

## From 6039 -> 1381

```
AUTOMATIC PAYMENT - THANK
AUTOMATIC PAYMENT - THANK YOU
Payment Thank You - Web
Payment Thank You-Mobile
```

## From 1605 -> 1381

```
Online Transfer from  CHK ...138
Online Transfer from  CHK ...1381 transaction#: xxxxxxxxxxx
Online Transfer from CHK ...1381
Online Transfer from CHK ...1381 transaction#:
Online Transfer from CHK ...1381 transaction#: xxxxxxxxxx
Online Transfer from CHK ...1381 transaction#: xxxxxxxxxxx
Online Transfer to CHK ...1381 t
Online Transfer to CHK ...1381 transaction#: xxxxxxxxxx xx/xx
Online Transfer to CHK ...1381 transaction#: xxxxxxxxxxx xx/xx
```
