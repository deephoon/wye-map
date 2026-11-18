# 온톨로지 요약 (data/ontology.json에서 생성 — 손으로 고치지 않음)

항목 종류(type)·계층·속성과, 관계 종류별 허용 끝점. `check.py`가 이 표 밖을 오류로 막는다.

## 계층

- `GOAL` 프로젝트 목표 — 이루려는 상태와 그것을 재는 기준
- `SCOPE` 대상 범위 — 이번에 다루는 공정·설비·제품·시스템·사람
- `CURRENT` 현재 방식 — 지금 일하고 판단하는 방식
- `PROBLEM` 핵심 문제 — 자료가 적은 현상과, 그것이 드러내는 목표를 막는 어긋남
- `TO_BE` 필요 조건 — 문제가 풀리려면 가능해야 하는 것
- `DATA_SYSTEM` 필요 데이터·시스템 — 판단에 쓸 데이터와 그것이 있는 곳
- `DECISION` 결정·제약 — 정한 것, 지켜야 할 조건, 전제

## 항목 종류

| type | 이름 | 계층 | 정의 | 속성 |
|---|---|---|---|---|
| `Project` | 프로젝트 | GOAL | 목표·범위·결정을 함께 관리하는 프로젝트. |  |
| `Goal` | 목표 | GOAL | 프로젝트가 달성하려는 결과. | `targetWindow` |
| `KPI` | 성과 기준 | GOAL | 결과나 상태를 측정하는 지표. | `formula`, `currentValue`, `targetValue`, `unit`, `aggregation` |
| `Stakeholder` | 관계자 | SCOPE | 업무에 참여하거나 책임을 가진 사람·조직. | `organization`, `role` |
| `Scope` | 대상 범위 | SCOPE | 프로젝트에서 다루는 대상과 그 경계. | `included`, `excluded` |
| `Product` | 제품·산출물 | SCOPE | 공정이 생산하거나 프로젝트가 제공하는 제품·산출물. |  |
| `CurrentPractice` | 현재 방식 | CURRENT | 현재 수행하는 작업이나 판단 방식. |  |
| `Observation` | 관찰 현상 | PROBLEM | 원문에서 관찰·기록된 현상. | `observedAt`, `condition` |
| `Problem` | 문제 | PROBLEM | 목표나 업무 수행을 방해한다고 판단한 문제. | `affectedObject`, `condition` |
| `Impact` | 영향 | PROBLEM | 문제가 업무·품질·비용 등에 미치는 결과. |  |
| `Requirement` | 요구사항 | TO_BE | 문제 해결을 위해 충족해야 할 조건·동작. | `applicationCondition` |
| `Capability` | 핵심 과제 | TO_BE | 필요한 업무 능력이나 핵심 과제. |  |
| `SolutionDirection` | 해결 방향 | TO_BE | 문제 해결을 위한 접근 방향. |  |
| `Solution` | 적용 후보 | TO_BE | 자료에서 적용 후보로 지정한 구체적 수단. |  |
| `UsageScenario` | 사용 장면 | TO_BE | 사용자가 특정 상황에서 수행하는 사용 장면. |  |
| `Screen` | 화면 | TO_BE | 사용자가 정보를 보고 조작하는 화면. |  |
| `DataRequirement` | 필요 데이터 | DATA_SYSTEM | 요구사항을 충족하는 데 필요한 데이터 묶음. | `sourceSystem`*, `unit`, `timing`, `joinKey`, `owner`, `availability`, `collectionMethod` |
| `DataItem` | 데이터 항목 | DATA_SYSTEM | 데이터를 구성하는 개별 항목. | `unit`, `grain`, `frequency` |
| `System` | 시스템 | DATA_SYSTEM | 업무나 데이터 처리를 수행하는 시스템. | `systemId`, `interface` |
| `Decision` | 결정 | DECISION | 근거와 이유를 가지고 채택한 판단. | `rationale`*, `alternatives`, `decidedBy`, `decidedAt` |
| `Constraint` | 제약 | DECISION | 수행을 제한하는 조건. | `condition` |
| `Assumption` | 전제 | DECISION | 확인 전 참으로 두고 진행하는 전제. | `condition` |
| `Process` | 공정 | SCOPE | 작업·변환이 수행되는 공정. | `processCode`, `line` |
| `Asset` | 설비 | SCOPE | 실제로 식별하고 관리하는 설비. | `assetCode`, `location` |

앵커(여기서 관계로 닿아야 맵에 오름): Project, Goal, Problem, Process

## 관계

| type | 출발 → 도착 | 읽는 법 |
|---|---|---|
| `BLOCKS` | Problem → Goal/Process | 출발이 도착을 막는다 (도착 쪽에서: 걸림돌) |
| `CAUSES` | CurrentPractice → Problem | 출발이 도착을 일으킨다 (도착 쪽에서: 원인) |
| `USES` | CurrentPractice → System/DataRequirement | 출발이 도착을 쓴다 (도착 쪽에서: 사용처) |
| `ADDRESSES` | Requirement/Capability → Problem | 출발이 도착을 해결한다 (도착 쪽에서: 해결 수단) |
| `DELIVERS` | Requirement/Capability → Goal | 출발이 도착을 기여한다 (도착 쪽에서: 기여 항목) |
| `NEEDS` | Requirement/Capability → DataRequirement | 출발이 도착을 필요로 한다 (도착 쪽에서: 활용처) |
| `PROVIDED_BY` | DataRequirement → System | 출발이 도착을 에서 나온다 (도착 쪽에서: 제공 데이터) |
| `MEASURES` | KPI → Goal/Process | 출발이 도착을 잰다 (도착 쪽에서: 측정 기준) |
| `IMPACTS` | Problem → Impact | 출발이 도착을 영향을 준다 (도착 쪽에서: 원인 문제) |
| `REALIZES` | SolutionDirection/Solution → Requirement/Capability | 출발이 도착을 실현한다 (도착 쪽에서: 실현 방안) |
| `FOLLOWS` | Solution → SolutionDirection | 출발이 도착을 따른다 (도착 쪽에서: 적용 후보) |
| `CONSTRAINS` | Constraint → Goal/Requirement/Capability/Solution/SolutionDirection/System/Process | 출발이 도착을 제약한다 (도착 쪽에서: 제약) |
| `OWNS` | Stakeholder → Problem/Requirement/DataRequirement/System/Decision/Process/Asset | 출발이 도착을 담당한다 (도착 쪽에서: 담당자) |
| `AFFECTS` | Decision → Goal/Problem/Requirement/Capability/DataRequirement/System/Process | 출발이 도착을 바꾼다 (도착 쪽에서: 관련 결정) |
| `HAS_GOAL` | Project → Goal | 출발이 도착을 목표로 둔다 (도착 쪽에서: 프로젝트) |
| `HAS_SCOPE` | Project → Scope | 출발이 도착을 범위로 둔다 (도착 쪽에서: 프로젝트) |
| `TARGETS` | Project → Product/System/Stakeholder/Process/Asset | 출발이 도착을 대상으로 한다 (도착 쪽에서: 대상 프로젝트) |
| `ASSUMES` | Project/Requirement/Solution → Assumption | 출발이 도착을 전제로 한다 (도착 쪽에서: 전제한 항목) |
| `INCLUDES` | Scope → Product/System/Stakeholder/Process/Asset | 출발이 도착을 포함한다 (도착 쪽에서: 속한 범위) |
| `PARTICIPATES_IN` | Stakeholder → Project | 출발이 도착을 참여한다 (도착 쪽에서: 참여자) |
| `OBSERVED_IN` | Observation → System/Product/Process/Asset | 출발이 도착을 에서 나타난다 (도착 쪽에서: 관찰 현상) |
| `INDICATES` | Observation → Problem | 출발이 도착을 드러낸다 (도착 쪽에서: 징후) |
| `HURTS` | Observation/Problem → KPI/Process | 출발이 도착을 나쁘게 한다 (도착 쪽에서: 악화 원인) |
| `JUDGES` | CurrentPractice → KPI/Observation | 출발이 도착을 판단한다 (도착 쪽에서: 현재 판단) |
| `INFORMS` | KPI → Decision | 출발이 도착을 뒷받침한다 (도착 쪽에서: 판단 근거) |
| `APPLIED_IN` | Decision/Requirement/Capability → UsageScenario | 출발이 도착을 에 쓰인다 (도착 쪽에서: 적용 항목) |
| `USED_BY` | UsageScenario/Screen → Stakeholder | 출발이 도착을 을 쓰는 사람 (도착 쪽에서: 사용 장면·화면) |
| `SHOWN_ON` | Requirement/Capability/KPI → Screen | 출발이 도착을 에 표시된다 (도착 쪽에서: 표시 항목) |
| `CONTAINS` | DataRequirement → DataItem | 출발이 도착을 담는다 (도착 쪽에서: 상위 데이터) |
| `STORED_IN` | DataItem → System | 출발이 도착을 에 저장된다 (도착 쪽에서: 저장 항목) |
| `PERFORMED_IN` | CurrentPractice → Process | 출발이 도착을 수행 공정 (도착 쪽에서: 작업 방식) |
| `SUPPORTS` | System/Asset → Process | 출발이 도착을 지원 대상 (도착 쪽에서: 지원 설비·시스템) |
| `PART_OF` | Process/Asset → Process | 출발이 도착을 상위 공정 (도착 쪽에서: 하위 항목) |
| `PRODUCES` | Process/Asset → Product | 출발이 도착을 산출물 (도착 쪽에서: 생산 공정·설비) |
