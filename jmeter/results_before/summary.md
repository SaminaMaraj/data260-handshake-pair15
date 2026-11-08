# JMeter results (Pair 15)

## CRUD endpoints

| Endpoint | Users | Samples | Avg (ms) | p95 (ms) | Throughput (req/s) | Error % |
|---|---|---|---|---|---|---|
| Login | 100 | 4190 | 1813 | 2629 | 45.9 | 0.00 |
| Login | 200 | 4271 | 3615 | 4862 | 45.8 | 0.00 |
| Login | 300 | 400807 | 58 | 18 | 4275.9 | 99.20 |
| Login | 400 | 529911 | 58 | 36 | 5659.2 | 99.44 |
| Login | 500 | 615575 | 62 | 52 | 6527.6 | 99.56 |
| Job search | 100 | 102732 | 73 | 128 | 1141.0 | 19.48 |
| Job search | 200 | 94936 | 158 | 295 | 1053.7 | 21.17 |
| Job search | 300 | 754247 | 30 | 61 | 8364.9 | 94.40 |
| Job search | 400 | 863850 | 35 | 81 | 9578.9 | 94.38 |
| Job search | 500 | 891921 | 42 | 148 | 9879.9 | 94.13 |
| Application submission | 100 | 80348 | 94 | 159 | 892.4 | 21.33 |
| Application submission | 200 | 64176 | 234 | 363 | 711.9 | 12.05 |
| Application submission | 300 | 16301 | 157 | 311 | 704.3 | 0.00 |
| Application submission | 400 | 124762 | 45 | 303 | 4285.7 | 87.96 |
| Application submission | 500 | 395580 | 43 | 112 | 8036.8 | 94.73 |
| Event search | 100 | 83955 | 89 | 170 | 932.6 | 16.69 |
| Event search | 200 | 67266 | 223 | 305 | 746.7 | 0.00 |
| Event search | 300 | 528781 | 43 | 303 | 5864.7 | 89.06 |
| Event search | 400 | 832495 | 36 | 41 | 9231.7 | 95.49 |
| Event search | 500 | 880835 | 43 | 47 | 9758.3 | 95.89 |

## Assistant endpoint

| Users | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Avg (ms) | Throughput (req/s) | Error % |
|---|---|---|---|---|---|---|---|
| 5 | 10 | 150068 | 150104 | 150108 | 142528 | 0.03 | 0.00 |
| 10 | 20 | 150052 | 150116 | 150117 | 149530 | 0.06 | 0.00 |
| 20 | 40 | 150104 | 150116 | 150120 | 150088 | 0.13 | 0.00 |
| 50 | 90 | 152072 | 180005 | 180008 | 157407 | 0.27 | 22.22 |

Response codes per run:

- Login @ 100: {'200': 4190}
- Login @ 200: {'200': 4271}
- Login @ 300: {'200': 3217, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 397590}
- Login @ 400: {'200': 2977, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 526934}
- Login @ 500: {'200': 2685, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 612890}
- Job search @ 100: {'200': 82721, '502': 20011}
- Job search @ 200: {'200': 74842, '502': 20094}
- Job search @ 300: {'200': 42274, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 711973}
- Job search @ 400: {'200': 48517, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 815333}
- Job search @ 500: {'200': 52389, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 838948, '502': 584}
- Application submission @ 100: {'409': 62244, '201': 963, '502': 17141}
- Application submission @ 200: {'409': 56385, '201': 58, '502': 7733}
- Application submission @ 300: {'409': 16062, '201': 239}
- Application submission @ 400: {'409': 14997, '201': 24, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 109741}
- Application submission @ 500: {'409': 20677, '201': 171, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 374732}
- Event search @ 100: {'200': 69941, '502': 14014}
- Event search @ 200: {'200': 67266}
- Event search @ 300: {'200': 57829, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 460711, '502': 10241}
- Event search @ 400: {'200': 37520, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 794975}
- Event search @ 500: {'200': 36195, 'Non HTTP response code: org.apache.http.NoHttpResponseException': 844640}
- Assistant chat @ 5: {'200': 10}
- Assistant chat @ 10: {'200': 20}
- Assistant chat @ 20: {'200': 40}
- Assistant chat @ 50: {'200': 70, '504': 20}
