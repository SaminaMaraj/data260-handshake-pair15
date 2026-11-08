# JMeter results (Pair 15)

## CRUD endpoints

| Endpoint | Users | Samples | Avg (ms) | p95 (ms) | Throughput (req/s) | Error % |
|---|---|---|---|---|---|---|
| Login | 100 | 3978 | 1910 | 2760 | 43.5 | 0.00 |
| Login | 200 | 4163 | 3690 | 4960 | 44.9 | 0.00 |
| Login | 300 | 4200 | 5558 | 7204 | 44.6 | 0.00 |
| Login | 400 | 4392 | 7149 | 9007 | 46.0 | 0.00 |
| Login | 500 | 4517 | 8857 | 11207 | 46.4 | 0.00 |
| Job search | 100 | 78820 | 95 | 132 | 875.6 | 0.00 |
| Job search | 200 | 75194 | 200 | 272 | 834.6 | 0.00 |
| Job search | 300 | 84214 | 268 | 352 | 934.4 | 0.00 |
| Job search | 400 | 75326 | 357 | 480 | 915.2 | 0.00 |
| Job search | 500 | 82736 | 455 | 592 | 916.7 | 0.00 |
| Application submission | 100 | 62838 | 120 | 176 | 698.0 | 0.00 |
| Application submission | 200 | 63158 | 238 | 325 | 700.8 | 0.00 |
| Application submission | 300 | 58823 | 384 | 524 | 652.0 | 0.00 |
| Application submission | 400 | 59620 | 505 | 674 | 659.9 | 0.00 |
| Application submission | 500 | 65663 | 574 | 740 | 726.2 | 0.00 |
| Event search | 100 | 78975 | 95 | 133 | 877.5 | 0.00 |
| Event search | 200 | 81009 | 185 | 264 | 899.2 | 0.00 |
| Event search | 300 | 75706 | 298 | 412 | 839.6 | 0.00 |
| Event search | 400 | 80808 | 372 | 504 | 895.3 | 0.00 |
| Event search | 500 | 67450 | 558 | 751 | 746.6 | 0.00 |

## Assistant endpoint

| Users | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Avg (ms) | Throughput (req/s) | Error % |
|---|---|---|---|---|---|---|---|
| 5 | 10 | 150068 | 150104 | 150108 | 142528 | 0.03 | 0.00 |
| 10 | 20 | 150052 | 150116 | 150117 | 149530 | 0.06 | 0.00 |
| 20 | 40 | 150104 | 150116 | 150120 | 150088 | 0.13 | 0.00 |
| 50 | 90 | 152072 | 180005 | 180008 | 157407 | 0.27 | 22.22 |

Response codes per run:

- Login @ 100: {'200': 3978}
- Login @ 200: {'200': 4163}
- Login @ 300: {'200': 4200}
- Login @ 400: {'200': 4392}
- Login @ 500: {'200': 4517}
- Job search @ 100: {'200': 78820}
- Job search @ 200: {'200': 75194}
- Job search @ 300: {'200': 84214}
- Job search @ 400: {'200': 75326}
- Job search @ 500: {'200': 82736}
- Application submission @ 100: {'409': 62598, '201': 240}
- Application submission @ 200: {'409': 63023, '201': 135}
- Application submission @ 300: {'409': 58809, '201': 14}
- Application submission @ 400: {'409': 59579, '201': 41}
- Application submission @ 500: {'409': 65529, '201': 134}
- Event search @ 100: {'200': 78975}
- Event search @ 200: {'200': 81009}
- Event search @ 300: {'200': 75706}
- Event search @ 400: {'200': 80808}
- Event search @ 500: {'200': 67450}
- Assistant chat @ 5: {'200': 10}
- Assistant chat @ 10: {'200': 20}
- Assistant chat @ 20: {'200': 40}
- Assistant chat @ 50: {'200': 70, '504': 20}
