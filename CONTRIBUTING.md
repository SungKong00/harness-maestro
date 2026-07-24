# Harness Maestro에 기여하기

사용자 설치·첫 실행은 [README](README.md), 현재 설계 권위와 문서 순서는
[문서 지도](docs/README.md)를 먼저 확인해 주세요.

## 개발 환경

Python 3.11 이상과 `uv`가 필요합니다.

```bash
git clone https://github.com/SungKong00/harness-maestro.git
cd harness-maestro
uv tool install --editable .
```

작은 버그 수정은 관련 테스트부터 실행하고, 완료 전에는 전체 검증을 수행합니다.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m maestro doctor --repo . --strict --json
```

세 Skill도 각각 bundled validator로 검사합니다.

```bash
skill_validator=/path/to/skill-creator/scripts/quick_validate.py
python3 "$skill_validator" skills/maestro
python3 "$skill_validator" skills/maestro-adapter-builder
python3 "$skill_validator" skills/maestro-govern
```

배포 경계가 바뀌면 wheel도 확인합니다.

```bash
uv build --wheel
python3 scripts/verify_wheel.py dist/harness_maestro-*.whl
```

## 변경 원칙

- 기존 사용자 변경과 managed block 밖의 본문을 보존합니다.
- CLI 출력이나 schema를 바꾸면 계약 테스트를 함께 갱신합니다.
- 새 Lens, Executor, Skill, Adapter, Convention은
  [구성요소 생명주기](docs/governance/component-lifecycle.md)의 admission rule을
  만족해야 합니다.
- 현재 규칙이 바뀌면 해당 활성 문서를 고칩니다. 중요한 선택의 이유가 바뀌면 ADR을
  추가하거나 기존 ADR을 supersede합니다.
- 실행 기록, 원시 연구 packet, 대화 전문을 새 Convention이나 활성 문서로 바로
  승격하지 않습니다.
- 작은 수정에 새 문서 계층이나 agent 역할을 추가하지 않습니다.

버그와 제안은 [Issues](https://github.com/SungKong00/harness-maestro/issues), 변경은
[Pull Requests](https://github.com/SungKong00/harness-maestro/pulls)로 제출합니다.
