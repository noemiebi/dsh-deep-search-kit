# facts — (보고서 주제)

기준 시점: YYYY-MM-DD. 자료 수집일: YYYY-MM-DD.
규칙: 본문에 쓰는 수치는 모두 여기 한 줄씩. 1차 출처 URL 을 적는다. 계산한 값은 계산식을 '정의' 칸에.
`build_pdf.py report.html -o 결과.pdf --facts facts.md` 로 PDF 본문 수치와 대조한다.

## 수치

| 수치 | 시점 | 지역 | 정의 | 출처 URL |
|---|---|---|---|---|
| 2,053만 대 | 2025 | 세계 | NEV(BEV+PHEV) 판매, +26% YoY | https://example.com/full/path |
| 76.4% | 2025 | 세계 | 중국 업체의 PHEV 점유율(업체 기준) | https://example.com/full/path |
| 25~30% | 2026~2028 | 유럽 | 추정 범위. 계산: 2026 Q2 30% (출처 ①), ACEA 상반기 25% (출처 ②) | https://example.com/full/path |
| 132% | 2026 | 중국 | 계산값: 43km → 100km 상향 = (100-43)/43 | https://example.com/full/path |

## 확인 못 한 것 / 상충 정보

- (찾았지만 1차 출처를 못 본 수치, 유료 자료)
- (기관마다 다른 수치: 정의·모집단과 함께)
