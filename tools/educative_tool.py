"""
tools/educative_tool.py — Educative.io course browser and content fetcher.
Opens Chrome locally with auth cookies, scrapes course structure, and saves for agent use.
"""

import os
import sys
import json
import base64
import subprocess
import tempfile
import time
from pathlib import Path

# -----------------------------------------------------------------------
# Cookies exported from educative.io browser (base64-encoded JSON objects,
# semicolon-separated). Rotate this when the session expires.
# -----------------------------------------------------------------------
_EDUCATIVE_COOKIES_B64 = (
    "eyJkb21haW4iOiJ3d3cuZWR1Y2F0aXZlLmlvIiwiZXhwaXJhdGlvbkRhdGUiOjE3OTYzMjE0"
    "MTQuOTc1NTE5LCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoiYWJf"
    "dGVzdGluZ19leHBsb3JlX2Ryb3Bkb3duIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3Bl"
    "Y2lmaWVkIiwic2VjdXJlIjpmYWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwi"
    "dmFsdWUiOiI4NiJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRl"
    "IjoxODEyNjc1MTUxLjMwMjU1NSwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2Us"
    "Im5hbWUiOiJfZ2EiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVjaWZpZWQiLCJzZWN1"
    "cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IkdBMS4x"
    "LjE2NzAxMjY2MDMuMTc2NDc4NTQzOCJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4"
    "cGlyYXRpb25EYXRlIjoxODEyNjc1MTUxLjcwNzIzMSwiaG9zdE9ubHkiOmZhbHNlLCJodHRw"
    "T25seSI6dHJ1ZSwibmFtZSI6IkZQSUQiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVj"
    "aWZpZWQiLCJzZWN1cmUiOnRydWUsInNlc3Npb24iOmZhbHNlLCJzdG9yZUlkIjoiMCIsInZh"
    "bHVlIjoiRlBJRDIuMi51bk9MVGFPN3pmRjMyQlhWNzNoM2tYV0pkbE40TXRwUXBXMWQ2TjUl"
    "MkJTd1UlM0QuMTc2NDc4NTQzOCJ9O3siZG9tYWluIjoid3d3LmVkdWNhdGl2ZS5pbyIsImV4"
    "cGlyYXRpb25EYXRlIjoxNzk2MzIxNDUxLjUzOTU5NywiaG9zdE9ubHkiOnRydWUsImh0dHBP"
    "bmx5IjpmYWxzZSwibmFtZSI6ImFiX3Rlc3RpbmciLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoi"
    "dW5zcGVjaWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6"
    "IjAiLCJ2YWx1ZSI6Ijc0In07eyJkb21haW4iOiJ3d3cuZWR1Y2F0aXZlLmlvIiwiZXhwaXJh"
    "dGlvbkRhdGUiOjE3OTkzNDU0NTAuMjAwMzk1LCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHki"
    "OmZhbHNlLCJuYW1lIjoidGhlbWUiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVjaWZp"
    "ZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1"
    "ZSI6ImRhcmsifTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0"
    "ZSI6MTc5OTM0NTQ1MC4yMDEwMzgsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6ZmFsc2Us"
    "Im5hbWUiOiJ1c2Vfc3lzdGVtX3ByZWZlcmVuY2UiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoi"
    "dW5zcGVjaWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6"
    "IjAiLCJ2YWx1ZSI6InBlcnNvbmFsIn07eyJkb21haW4iOiJ3d3cuZWR1Y2F0aXZlLmlvIiwi"
    "ZXhwaXJhdGlvbkRhdGUiOjE4MDk2NTExNTEsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6"
    "ZmFsc2UsIm5hbWUiOiJ1c3ByaXZhY3kiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoibGF4Iiwi"
    "c2VjdXJlIjpmYWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIx"
    "LS0tIn07eyJkb21haW4iOiIuZWR1Y2F0aXZlLmlvIiwiZXhwaXJhdGlvbkRhdGUiOjE3OTM2"
    "NjcxNTEsImhvc3RPbmx5IjpmYWxzZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoiaHVic3Bv"
    "dHV0ayIsInBhdGgiOiIvIiwic2FtZVNpdGUiOiJsYXgiLCJzZWN1cmUiOmZhbHNlLCJzZXNz"
    "aW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IjZkOTlkNjU4OWZlYzZlNWFmNTM5"
    "MzI0YWY5YTYzMjU0In07eyJkb21haW4iOiIuZWR1Y2F0aXZlLmlvIiwiZXhwaXJhdGlvbkRh"
    "dGUiOjE3ODU4OTExNTEsImhvc3RPbmx5IjpmYWxzZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1l"
    "IjoiX2ZicCIsInBhdGgiOiIvIiwic2FtZVNpdGUiOiJsYXgiLCJzZWN1cmUiOmZhbHNlLCJz"
    "ZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6ImZiLjEuMTc2NDc4NTYzMDE3"
    "My45NzY2NzIyMTYxOTc5MDk5NDcifTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJl"
    "eHBpcmF0aW9uRGF0ZSI6MTgwOTY1MTE0NCwiaG9zdE9ubHkiOnRydWUsImh0dHBPbmx5Ijpm"
    "YWxzZSwibmFtZSI6Ik9uZVRydXN0V1BDQ1BBR29vZ2xlT3B0T3V0IiwicGF0aCI6Ii8iLCJz"
    "YW1lU2l0ZSI6ImxheCIsInNlY3VyZSI6ZmFsc2UsInNlc3Npb24iOmZhbHNlLCJzdG9yZUlk"
    "IjoiMCIsInZhbHVlIjoiZmFsc2UifTt7ImRvbWFpbiI6Ii53d3cuZWR1Y2F0aXZlLmlvIiwi"
    "ZXhwaXJhdGlvbkRhdGUiOjE3OTcyNDkwMDQsImhvc3RPbmx5IjpmYWxzZSwiaHR0cE9ubHki"
    "OmZhbHNlLCJuYW1lIjoiX19zdHJpcGVfbWlkIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InN0"
    "cmljdCIsInNlY3VyZSI6dHJ1ZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFs"
    "dWUiOiIwNTgzYmNhMi0wYjYxLTRjZDQtOWUzOS1mMDViYWE3MjRjOGM1ZGQ4M2MifTt7ImRv"
    "bWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTgwMDI3MzA2Ny41"
    "OTc0ODMsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJob2xpZGF5"
    "QmFubmVyIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjpm"
    "YWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiJ0cnVlIn07eyJk"
    "b21haW4iOiIud3d3LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxODExMDE4ODQ5"
    "LjUzMjY5OCwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJfZ2Ff"
    "TVdHU0dDVzVTUCIsInBhdGgiOiIvIiwic2FtZVNpdGUiOiJ1bnNwZWNpZmllZCIsInNlY3Vy"
    "ZSI6ZmFsc2UsInNlc3Npb24iOmZhbHNlLCJzdG9yZUlkIjoiMCIsInZhbHVlIjoiZGVsZXRl"
    "ZCJ9O3siZG9tYWluIjoid3d3LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxODEx"
    "MDE4ODQ5LjUzMzM1MiwiaG9zdE9ubHkiOnRydWUsImh0dHBPbmx5IjpmYWxzZSwibmFtZSI6"
    "Il9nYV9NV0dTR0NXNVNQIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwi"
    "c2VjdXJlIjpmYWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiJk"
    "ZWxldGVkIn07eyJkb21haW4iOiJ3d3cuZWR1Y2F0aXZlLmlvIiwiZXhwaXJhdGlvbkRhdGUi"
    "OjE3ODE0OTgxNDQuNTk4MjA4LCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHkiOmZhbHNlLCJu"
    "YW1lIjoiYWJfdGVzdF9oYXNoIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6ImxheCIsInNlY3Vy"
    "ZSI6dHJ1ZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiI0NyJ9O3si"
    "ZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxNzgyMDE2NTQ4LCJo"
    "b3N0T25seSI6ZmFsc2UsImh0dHBPbmx5IjpmYWxzZSwibmFtZSI6Il9nY2xfYXUiLCJwYXRo"
    "IjoiLyIsInNhbWVTaXRlIjoidW5zcGVjaWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9u"
    "IjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IjEuMS44ODA3MjQxMC4xNzc0MjQwNTQ4"
    "In07eyJkb21haW4iOiJ3d3cuZWR1Y2F0aXZlLmlvIiwiZXhwaXJhdGlvbkRhdGUiOjE3Nzk5"
    "Mjk1NTMuNjczNjAyLCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoi"
    "bG9nZ2VkX2luIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJl"
    "Ijp0cnVlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6InRydWUifTt7"
    "ImRvbWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTc4MzU0MTUwNCwi"
    "aG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJfZ2NsX2dzIiwicGF0"
    "aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjpmYWxzZSwic2Vzc2lv"
    "biI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIyLjEuazEkaTE3NzU3NjU0OTIkdTEy"
    "MTQxNDYyMCJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjox"
    "NzgzNTQxNTA0LCJob3N0T25seSI6ZmFsc2UsImh0dHBPbmx5IjpmYWxzZSwibmFtZSI6Il9n"
    "Y2xfYXciLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVjaWZpZWQiLCJzZWN1cmUiOmZh"
    "bHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IkdDTC4xNzc1NzY1"
    "NTA0LkNqd0tDQWp3bk4zT0JoQThFaXdBZnBUWWV2dmRsbWx3WVh5NkhCT1ZySzZ4RXJTNUl1"
    "MEtlV3poWEl0SW5SYmdocWx6ZDIyNjFjbVRYUm9DSmZ3UUF2RF9Cd0UifTt7ImRvbWFpbiI6"
    "Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTc3ODExNjk0MS41NTU1ODQsImhv"
    "c3RPbmx5IjpmYWxzZSwiaHR0cE9ubHkiOnRydWUsIm5hbWUiOiJfX2NmX2JtIiwicGF0aCI6"
    "Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjp0cnVlLCJzZXNzaW9uIjpm"
    "YWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IktHbHpKdzFvdHYuTEY4V1lDbVdnWDEydGdp"
    "cTRDYU9VUTh5eHRONnV3ZEktMTc3ODExNTE0MS40OTk5MzMyLTEuMC4xLjEtQXQzUk1McFZI"
    "SXBnbEo0dGVRd0FaeGxNQmFMdEpJUXltcWpPRjJrVUY4c09VUmZubGlXWjVULjJValZIMzFi"
    "bWN1cXVkdkU0d0pmV0NvTElpYkVpcFZfS2JhbXlCTGdPLm5nU2diOFpHbDREYXlWZGZHcThR"
    "S1BweFdNN1FmU0IifTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJob3N0T25seSI6"
    "dHJ1ZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoidHJpYWxfYXZhaWxlZCIsInBhdGgiOiIv"
    "Iiwic2FtZVNpdGUiOiJ1bnNwZWNpZmllZCIsInNlY3VyZSI6ZmFsc2UsInNlc3Npb24iOnRy"
    "dWUsInN0b3JlSWQiOiIwIiwidmFsdWUiOiJmYWxzZSJ9O3siZG9tYWluIjoid3d3LmVkdWNh"
    "dGl2ZS5pbyIsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJzdWJz"
    "Y3JpYmVkIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjpm"
    "YWxzZSwic2Vzc2lvbiI6dHJ1ZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6InRydWUifTt7ImRv"
    "bWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHkiOmZh"
    "bHNlLCJuYW1lIjoibDJjX3N1YnNjcmliZWQiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5z"
    "cGVjaWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjp0cnVlLCJzdG9yZUlkIjoiMCIs"
    "InZhbHVlIjoiZmFsc2UifTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJleHBpcmF0"
    "aW9uRGF0ZSI6MTc3OTkyOTU1My42NzM3ODgsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6"
    "dHJ1ZSwibmFtZSI6ImZsYXNrLWF1dGgiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVj"
    "aWZpZWQiLCJzZWN1cmUiOnRydWUsInNlc3Npb24iOmZhbHNlLCJzdG9yZUlkIjoiMCIsInZh"
    "bHVlIjoiLmVKeUxOalV3TXpjM05UYzF0akEwTkRXMU1ORXgwRkZ5elVsT05zMHFxelFLOVRj"
    "eU5YVlA5c254OXdrdlZnSktBU1V6akF5TVRBME16U3dkQ2pKekV2TXk5Wkl5UzRwMW9lekVa"
    "TDNNUENYaUZKVVVsYWJxcENYbUZLZnE1SlhtNU9nWVF5aERjM09RVXd4TmpHSUJ2eTh1cHci"
    "fTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTc3ODIw"
    "MTQ5Mi42MTA4NDIsImhvc3RPbmx5Ijp0cnVlLCJodHRwT25seSI6dHJ1ZSwibmFtZSI6ImNh"
    "Y2hlX3Rva2VuIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJl"
    "IjpmYWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIxNzc4MTE1"
    "MTQzLTlUanlnVVNVczZqSFJka3RwOTBRSzVPcU8wVzhaejFObzdlakgxRE5jd2clM0QifTt7"
    "ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJob3N0T25seSI6dHJ1ZSwiaHR0cE9ubHki"
    "OmZhbHNlLCJuYW1lIjoicmVjb21tZW5kYXRpb25zIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6"
    "InVuc3BlY2lmaWVkIiwic2VjdXJlIjpmYWxzZSwic2Vzc2lvbiI6dHJ1ZSwic3RvcmVJZCI6"
    "IjAiLCJ2YWx1ZSI6InRydWUifTt7ImRvbWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0"
    "aW9uRGF0ZSI6MTc5MzY2NzE1MSwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2Us"
    "Im5hbWUiOiJfX2hzdGMiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoibGF4Iiwic2VjdXJlIjpm"
    "YWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIxMDQ0OTg5OC42"
    "ZDk5ZDY1ODlmZWM2ZTVhZjUzOTMyNGFmOWE2MzI1NC4xNzY0Nzg1NTI3MzkwLjE3Nzc0Nzk1"
    "Njk0MDguMTc3ODExNTE0NDUyNC43MSJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImhv"
    "c3RPbmx5IjpmYWxzZSwiaHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoiX19oc3NyYyIsInBhdGgi"
    "OiIvIiwic2FtZVNpdGUiOiJsYXgiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjp0cnVlLCJz"
    "dG9yZUlkIjoiMCIsInZhbHVlIjoiMSJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4"
    "cGlyYXRpb25EYXRlIjoxNzc4MTg3MTQ0LjYxOTgyNywiaG9zdE9ubHkiOmZhbHNlLCJodHRw"
    "T25seSI6ZmFsc2UsIm5hbWUiOiJGUExDIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3Bl"
    "Y2lmaWVkIiwic2VjdXJlIjp0cnVlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2"
    "YWx1ZSI6ImtrTnQyUmZaZzd4cUl6WFkwRjdhcG5WNmNKR1VGWWJHYXRHSmZVMTQzYnBDZUc5"
    "UVIzYWFJaDhRZWVja3RhcUU1dTVsTmZLeUVGVGpqZlZzWU5ERHBuaGFmZW1TaWFVanVkTEpH"
    "b3U1SlIlMkZ0bFR4Y2FZTWlpQVJkTXpSZWh3JTNEJTNEIn07eyJkb21haW4iOiIuZWR1Y2F0"
    "aXZlLmlvIiwiZXhwaXJhdGlvbkRhdGUiOjE4MDk2NTExNDQsImhvc3RPbmx5IjpmYWxzZSwi"
    "aHR0cE9ubHkiOmZhbHNlLCJuYW1lIjoiX2NsY2siLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoi"
    "dW5zcGVjaWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6"
    "IjAiLCJ2YWx1ZSI6ImRmYTRwMSU1RTIlNUVnNXUlNUUwJTVFMjE2MyJ9O3siZG9tYWluIjoi"
    "LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxNzg1ODkxMTUxLCJob3N0T25seSI6"
    "ZmFsc2UsImh0dHBPbmx5IjpmYWxzZSwibmFtZSI6Il9yZHRfdXVpZCIsInBhdGgiOiIvIiwi"
    "c2FtZVNpdGUiOiJzdHJpY3QiLCJzZWN1cmUiOnRydWUsInNlc3Npb24iOmZhbHNlLCJzdG9y"
    "ZUlkIjoiMCIsInZhbHVlIjoiMTc2NDc4NTQ3MDY5My5jNDIxMTQzMC01NTAxLTRmMGMtYjJl"
    "MS1mMDIzNDMzNTRmZWUifTt7ImRvbWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9u"
    "RGF0ZSI6MTc3ODExNjk1MSwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5h"
    "bWUiOiJfX2hzc2MiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoibGF4Iiwic2VjdXJlIjpmYWxz"
    "ZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIxMDQ0OTg5OC4yLjE3"
    "NzgxMTUxNDQ1MjQifTt7ImRvbWFpbiI6Ind3dy5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9u"
    "RGF0ZSI6MTc5MzY2NzE1MSwiaG9zdE9ubHkiOnRydWUsImh0dHBPbmx5IjpmYWxzZSwibmFt"
    "ZSI6Imdfc3RhdGUiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVjaWZpZWQiLCJzZWN1"
    "cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IntcImlf"
    "bFwiOjAsXCJpX2xsXCI6MTc3ODExNTE1MTI4NSxcImlfZVwiOntcImVuYWJsZV9pdHBfb3B0"
    "aW1pemF0aW9uXCI6MH0sXCJpX2JcIjpcIndoMmlKZGgvLzJBQWRuV3dScjdTSFd2ektHNTFn"
    "aUxTRWtDT3FHMk52L29cIixcImlfZXRcIjoxNzc2Mzc5NjgzNzM0fSJ9O3siZG9tYWluIjoi"
    "LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxODA5NjUxMTUxLCJob3N0T25seSI6"
    "ZmFsc2UsImh0dHBPbmx5IjpmYWxzZSwibmFtZSI6Ik9wdGFub25Db25zZW50IiwicGF0aCI6"
    "Ii8iLCJzYW1lU2l0ZSI6ImxheCIsInNlY3VyZSI6ZmFsc2UsInNlc3Npb24iOmZhbHNlLCJz"
    "dG9yZUlkIjoiMCIsInZhbHVlIjoiaXNHcGNFbmFibGVkPTAmZGF0ZXN0YW1wPVRodStNYXkr"
    "MDcrMjAyNiswNiUzQTIyJTNBMzErR01UJTJCMDUzMCsoSW5kaWErU3RhbmRhcmQrVGltZSkm"
    "dmVyc2lvbj0yMDI1MDkuMS4wJmJyb3dzZXJHcGNGbGFnPTAmaXNJQUJHbG9iYWw9ZmFsc2Um"
    "aG9zdHM9JmNvbnNlbnRJZD1jMTFhOGZmZS1mYzE3LTRkYzEtYWRhZS1jMWM5Mzg2NDEyNjIm"
    "aW50ZXJhY3Rpb25Db3VudD0xJmlzQW5vblVzZXI9MSZsYW5kaW5nUGF0aD1Ob3RMYW5kaW5n"
    "UGFnZSZncm91cHM9QzAwMDElM0ExJTJDQzAwMDIlM0ExJTJDQzAwMDMlM0ExJTJDQzAwMDQl"
    "M0ExJkF3YWl0aW5nUmVjb25zZW50PWZhbHNlJmdlb2xvY2F0aW9uPUlOJTNCUkoifTt7ImRv"
    "bWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTgwOTY1MTE1MSwiaG9z"
    "dE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJPcHRhbm9uQWxlcnRCb3hD"
    "bG9zZWQiLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoibGF4Iiwic2VjdXJlIjpmYWxzZSwic2Vz"
    "c2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIyMDI2LTA1LTA3VDAwOjUyOjMx"
    "LjMwNFoifTt7ImRvbWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6MTc3"
    "ODIwMTU1MSwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJfdWV0"
    "c2lkIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjpmYWxz"
    "ZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIwMzBiYzY4MDQ5YWYx"
    "MWYxYTZjYmJkYmUyMmQzMjcxYXwxNjhwaXlrfDJ8ZzV1fDB8MjMxOCJ9O3siZG9tYWluIjoi"
    "LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxNzc4MTE2OTQ0LjcwNzI3NSwiaG9z"
    "dE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJGUEdTSUQiLCJwYXRoIjoi"
    "LyIsInNhbWVTaXRlIjoic3RyaWN0Iiwic2VjdXJlIjp0cnVlLCJzZXNzaW9uIjpmYWxzZSwi"
    "c3RvcmVJZCI6IjAiLCJ2YWx1ZSI6IjEuMTc3ODExNTE0NC4xNzc4MTE1MTUxLkctTVdHU0dD"
    "VzVTUC40Zzdpal9hVzd4eThwYjFuRDlwUHhRIn07eyJkb21haW4iOiIuZWR1Y2F0aXZlLmlv"
    "IiwiZXhwaXJhdGlvbkRhdGUiOjE3NzgyMDE1NTIsImhvc3RPbmx5IjpmYWxzZSwiaHR0cE9u"
    "bHkiOmZhbHNlLCJuYW1lIjoiX2Nsc2siLCJwYXRoIjoiLyIsInNhbWVTaXRlIjoidW5zcGVj"
    "aWZpZWQiLCJzZWN1cmUiOmZhbHNlLCJzZXNzaW9uIjpmYWxzZSwic3RvcmVJZCI6IjAiLCJ2"
    "YWx1ZSI6IjlrZTBoMSU1RTE3NzgxMTUxNTIyNDMlNUUyJTVFMSU1RW8uY2xhcml0eS5tcyUy"
    "RmNvbGxlY3QifTt7ImRvbWFpbiI6Ii5lZHVjYXRpdmUuaW8iLCJleHBpcmF0aW9uRGF0ZSI6"
    "MTgxMTgxMTE1MiwiaG9zdE9ubHkiOmZhbHNlLCJodHRwT25seSI6ZmFsc2UsIm5hbWUiOiJf"
    "dWV0dmlkIiwicGF0aCI6Ii8iLCJzYW1lU2l0ZSI6InVuc3BlY2lmaWVkIiwic2VjdXJlIjpm"
    "YWxzZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiI3MzQzZTg5MGQw"
    "NzMxMWYwYWRmNzFiOTI4MzEyZDI4NHwxdDhzMmU4fDE3NzgxMTUxNTIzMDB8MnwxfGJhdC5i"
    "aW5nLmNvbS9wL2luc2lnaHRzL2MvbyJ9O3siZG9tYWluIjoiLmVkdWNhdGl2ZS5pbyIsImV4"
    "cGlyYXRpb25EYXRlIjoxNzc4MjAxNTUzLjY3MzcwMywiaG9zdE9ubHkiOmZhbHNlLCJodHRw"
    "T25seSI6dHJ1ZSwibmFtZSI6Im1hZ2ljYm94LWF1dGgiLCJwYXRoIjoiLyIsInNhbWVTaXRl"
    "IjoidW5zcGVjaWZpZWQiLCJzZWN1cmUiOnRydWUsInNlc3Npb24iOmZhbHNlLCJzdG9yZUlk"
    "IjoiMCIsInZhbHVlIjoiZXlKMWMyVnlYMmxrSWpvZ05UQTJOemMxTnpVek9ERXhOVFU0TkN3"
    "Z0luUnZhMlZ1SWpvZ0lqQnVUMEo0Um1SQlJXeFFOa0pVUlZKdFJGYzNVR2dpTENBaWRHOXJa"
    "VzVmZEhNaU9pQXhOemM0TVRFMU1UVXpNREF3TENBaWJHOTFYM05sYzNOcGIyNGlPaUJtWVd4"
    "elpYMD18MzVlNTdkZmRmNDViZTFiNWNkNTkwOTg5MmU0ZThiMjJmZjc3NWMxYiJ9O3siZG9t"
    "YWluIjoid3d3LmVkdWNhdGl2ZS5pbyIsImV4cGlyYXRpb25EYXRlIjoxNzc5OTI5NTUzLjY3"
    "Mzg1NiwiaG9zdE9ubHkiOnRydWUsImh0dHBPbmx5Ijp0cnVlLCJuYW1lIjoiZmxhc2stc2Vz"
    "c2lvbiIsInBhdGgiOiIvIiwic2FtZVNpdGUiOiJ1bnNwZWNpZmllZCIsInNlY3VyZSI6dHJ1"
    "ZSwic2Vzc2lvbiI6ZmFsc2UsInN0b3JlSWQiOiIwIiwidmFsdWUiOiIuZUp5clZvb3ZTQzNL"
    "VGN4THpTdFJzaW9wS2szVlVZb3ZMVTR0VXJLS05qVXdNemMzTlRjMXRqQTBORFcxTU5FeDBG"
    "Unl6VWxPTnMwcXF6UUs5VGN5TlhWUDlzbng5d2t2VmdKS0FTVXpqQXlNVEEwTXpTd2RDakp6"
    "RXZNeTlaSXlTNHAxb2V6RVpMM01QQ1hpRklIZGtaYVlVNXlxazFlYWs2TmpES0VNemMxQlRq"
    "RTBNWXd0QlFCeUpqak8uYWZ2aVVRLkxUVVU2YzlBRmd4OE5zM3ZtOGc4ZDMzY2dvVSJ9"
)

WORKSPACE_HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_workspace"))
COURSES_DIR = os.path.join(WORKSPACE_HOST, "educative_courses")


def _decode_cookies(cookie_str: str) -> list:
    """Decode the cookie blob.

    The stored value is a SINGLE base64 string whose decoded form is
    a semicolon-separated list of JSON cookie objects, e.g.:
        {name:..., value:...};{name:..., value:...};...
    """
    cookie_str = "".join(cookie_str.split())  # strip all whitespace / line breaks
    padding = (4 - len(cookie_str) % 4) % 4
    try:
        decoded = base64.b64decode(cookie_str + "=" * padding).decode("utf-8")
    except Exception:
        return []

    cookies = []
    for part in decoded.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            cookies.append(json.loads(part))
        except Exception:
            pass
    return cookies


def _to_playwright_cookies(raw_cookies: list) -> list:
    """Convert raw cookie dicts to Playwright-compatible format."""
    pw_cookies = []
    for c in raw_cookies:
        domain = c.get("domain", "")
        # Playwright hostOnly cookies must not have a leading dot
        if c.get("hostOnly") and domain.startswith("."):
            domain = domain[1:]

        pw_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": domain,
            "path": c.get("path", "/"),
        }
        if "expirationDate" in c:
            pw_cookie["expires"] = int(c["expirationDate"])
        if c.get("secure"):
            pw_cookie["secure"] = True
        if c.get("httpOnly"):
            pw_cookie["httpOnly"] = True

        same_site = c.get("sameSite", "unspecified").lower()
        if same_site == "lax":
            pw_cookie["sameSite"] = "Lax"
        elif same_site == "strict":
            pw_cookie["sameSite"] = "Strict"
        elif same_site == "none":
            pw_cookie["sameSite"] = "None"

        pw_cookies.append(pw_cookie)
    return pw_cookies


# ---------------------------------------------------------------------------
# Playwright browser script (runs locally on the host, not inside Docker)
# ---------------------------------------------------------------------------
_BROWSER_SCRIPT_TEMPLATE = """
import json, sys, time
from playwright.sync_api import sync_playwright

URL = {url}
OUTPUT_FILE = {output_file}
COOKIES = {cookies}

def extract_course_content(page):
    try:
        return page.evaluate('''() => {{
            const r = {{title:"",description:"",url:window.location.href,lessons:[],current_content:""}};
            const h1 = document.querySelector("h1, .course-title, [data-testid='course-title']");
            if (h1) r.title = h1.textContent.trim();
            const desc = document.querySelector(".course-description, .description");
            if (desc) r.description = desc.textContent.trim().slice(0,600);

            // Sidebar / table of contents — try many selectors educative uses
            const selectors = [
                "[class*='SideBarItem']",
                "[class*='sidebar-item']",
                "[class*='lesson-item']",
                ".lesson-list-item",
                ".chapter-item",
                "li[class*='item']",
                "nav a",
                "[class*='TableOfContents'] a",
                "[class*='toc'] a"
            ];
            const seen = new Set();
            for (const sel of selectors) {{
                document.querySelectorAll(sel).forEach(el => {{
                    const link = el.tagName === "A" ? el : el.querySelector("a");
                    const text = el.textContent.trim().slice(0,200);
                    const href = link ? link.href : null;
                    const key = text + "|" + href;
                    if (text.length > 2 && !seen.has(key)) {{
                        seen.add(key);
                        r.lessons.push({{title:text, url:href}});
                    }}
                }});
                if (r.lessons.length > 5) break;
            }}
            r.lessons = r.lessons.slice(0, 120);

            const main = document.querySelector("main, article, .content, .lesson-content");
            if (main) r.current_content = main.textContent.trim().slice(0,3000);
            return r;
        }}''')
    except Exception as e:
        return {{"error": str(e), "url": page.url}}

with sync_playwright() as p:
    print("Opening Chrome...", flush=True)
    try:
        browser = p.chromium.launch(headless=False, channel="chrome",
                                    args=["--start-maximized"])
    except Exception:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])

    ctx = browser.new_context(
        viewport={{"width": 1920, "height": 1080}},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    print(f"Injecting {{len(COOKIES)}} cookies...", flush=True)
    try:
        ctx.add_cookies(COOKIES)
    except Exception as e:
        print(f"Cookie warning: {{e}}", flush=True)

    page = ctx.new_page()
    print(f"Navigating to {{URL}} ...", flush=True)
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(4000)
        data = extract_course_content(page)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("COURSE_DATA:" + json.dumps(data), flush=True)
    except Exception as e:
        err = {{"error": str(e), "url": URL}}
        print("COURSE_DATA:" + json.dumps(err), flush=True)

    # Stay open so the user can browse
    print("Browser ready. Close the window when done.", flush=True)
    try:
        page.wait_for_timeout(600000)  # 10 min max then auto-close
    except Exception:
        pass
    browser.close()
"""


def open_educative_course(url: str) -> dict:
    """
    Open Chrome with educative.io auth cookies, navigate to the given course URL,
    scrape the course structure, save it to workspace, and return a summary.
    The browser stays open so the user can interact with the course.
    """
    os.makedirs(COURSES_DIR, exist_ok=True)

    raw_cookies = _decode_cookies(_EDUCATIVE_COOKIES_B64)
    pw_cookies = _to_playwright_cookies(raw_cookies)

    url_slug = url.split("educative.io/")[-1].replace("/", "_").replace("?", "_")[:80]
    output_file = os.path.join(COURSES_DIR, f"{url_slug}.json")

    script_body = _BROWSER_SCRIPT_TEMPLATE.format(
        url=json.dumps(url),
        output_file=json.dumps(output_file),
        cookies=json.dumps(pw_cookies),
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="educ_"
    ) as f:
        f.write(script_body)
        script_path = f.name

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        course_data = None
        lines = []
        deadline = time.time() + 50  # 50 s to get content back

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.3)
                continue
            lines.append(line.rstrip())
            if line.startswith("COURSE_DATA:"):
                try:
                    course_data = json.loads(line[len("COURSE_DATA:"):])
                except Exception:
                    pass
                break

        if course_data and "error" not in course_data:
            return {
                "success": True,
                "message": (
                    "Chrome is open and logged into educative.io. "
                    "Course content extracted and saved. Browser stays open."
                ),
                "course": {
                    "title": course_data.get("title", ""),
                    "description": course_data.get("description", ""),
                    "url": url,
                    "lesson_count": len(course_data.get("lessons", [])),
                    "lessons": course_data.get("lessons", [])[:30],
                },
                "saved_to": f"/workspace/educative_courses/{os.path.basename(output_file)}",
                "browser_pid": proc.pid,
            }
        else:
            return {
                "success": False,
                "message": "Chrome opened but content extraction timed out or failed.",
                "log": "\n".join(lines[-20:]),
                "error": course_data.get("error") if course_data else "timeout",
                "browser_pid": getattr(proc, "pid", None),
                "hint": (
                    "Playwright may not be installed locally. "
                    "Run: pip install playwright && playwright install chrome"
                ),
            }
    except FileNotFoundError:
        return {
            "error": "Playwright not found. Install with: pip install playwright && playwright install chrome"
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def load_educative_course(filename: str) -> dict:
    """Load a previously saved educative course JSON from the workspace."""
    for candidate in [
        os.path.join(COURSES_DIR, filename),
        os.path.join(WORKSPACE_HOST, filename),
        filename,
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    data = json.load(f)
                return {"success": True, "data": data}
            except Exception as e:
                return {"error": str(e)}
    return {"error": f"File not found: {filename}"}


def list_educative_courses() -> dict:
    """List all educative courses that have been saved to the workspace."""
    if not os.path.exists(COURSES_DIR):
        return {"courses": [], "message": "No courses saved yet. Use open_educative_course first."}

    files = sorted(
        f for f in os.listdir(COURSES_DIR) if f.endswith(".json")
    )
    courses = []
    for fname in files:
        try:
            with open(os.path.join(COURSES_DIR, fname)) as fh:
                d = json.load(fh)
            courses.append({
                "filename": fname,
                "title": d.get("title", fname),
                "url": d.get("url", ""),
                "lesson_count": len(d.get("lessons", [])),
            })
        except Exception:
            courses.append({"filename": fname, "title": fname})

    return {"courses": courses, "count": len(courses)}
