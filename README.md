---
title: 한의처방 AI
emoji: 🌿
colorFrom: green
colorTo: red
sdk: gradio
sdk_version: "5.23.3"
app_file: app.py
pinned: false
license: mit
---

# 한의처방 AI (Korean Traditional Medicine Prescription System)

방약합편 532개 처방 기반 한의학 처방 검색 및 추천 시스템

## 기능

| 탭 | 기능 | 설명 |
|---|---|---|
| 증상 검색 | 증상 입력 → 처방 추천 | TF-IDF + 가중 유사도 기반 |
| 처방 상세 | 처방명 → 구성/주치/적용증/치험례 | Obsidian vault 파싱 |
| 유사 처방 | Jaccard 유사도 + 약재 차이 분석 | 기능/체질/질병양상 비교 |
| 치험례 RAG | ChromaDB 벡터 검색 | 2,392건 임상 사례 |
| 체질 평가 | 5레이어 체질 객관화 지수 | BMI/HCI/DEI/사상체질 |
| 임상논문 | PubMed E-utilities 검색 | API 키 불필요 |

## 데이터

- **방약합편** 532개 처방 (상통/중통/하통)
- **SQLite DB** 527개 처방, 2,392건 치험례
- **약재 기능 사전** 170+ 약재 카테고리/효능/타겟
- **플로우차트** .canvas 기반 처방 관계도

## 로컬 실행

```bash
pip install -r requirements.txt
python app.py
```

http://localhost:7860 에서 접속

## 기술 스택

Python + Gradio + SQLite + ChromaDB + scikit-learn + NetworkX
