# Third-party notices

## DeepSeek Harness (DSH)

`profiles/web/deep-search.patch.yml` is derived from `presets/standard.patch.yml` of
`@deepseek-ai/dsh-web-app` 0.2.1-rc.2 (plugin list and the plan-mode instruction text are copied
as is; the name, description and persona research rules were changed). That file is distributed
under the following license:

```
MIT License

Copyright (c) 2026 DeepSeek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 외부 프로그램 (포함하지 않음)

이 저장소는 아래 프로그램을 **포함하거나 재배포하지 않고**, 사용자 컴퓨터에 설치된 것을 실행만 합니다.

- poppler (`pdftotext`, `pdfinfo` 등) — GPL. 별도 명령으로 호출만 합니다.
- Google Chrome — PDF 렌더에 사용(headless).
- xlrd — `.xls` 읽기에 사용(BSD). 사용자가 직접 설치합니다.
- matplotlib — 차트(사용자 환경). `tools/matplotlibrc`는 설정 파일일 뿐 글꼴 파일을 포함하지 않습니다.

## 상표

DeepSeek은 DeepSeek의, 한/글·HWP·HWPX는 한글과컴퓨터의, Microsoft Excel은 Microsoft의, Exa는 Exa Labs의 상표입니다.
이 저장소는 위 회사들과 관계없는 개인 설정이며, 이름은 호환 대상을 설명하려고만 씁니다.
