# OpenSUSI × Google AI 支援チップ設計プラットフォーム — MPW 設計テンプレート (`NEW-130E_MPW_template`)

> Language: [English (README.md)](README.md) | **日本語**

OpenSUSI × Google AI 支援チップ設計プラットフォーム向けの標準 **GitHub-to-Silicon** チップ設計リポジトリテンプレートです。

- **本番ターゲット PDK**: **NEW-130E**（新 130 nm CMOS ファウンドリ PDK — アダプタプロファイル: [`pdk/profiles/new130e.yaml`](pdk/profiles/new130e.yaml)、統合ガイド: [`pdk/profiles/new130e.md`](pdk/profiles/new130e.md)）
- **対応済みオープン 130 nm PDK（Git Submodule 運用）**:
  - **IHP-130 (`SG13G2`)** — [`pdk/profiles/ihp_sg13g2.yaml`](pdk/profiles/ihp_sg13g2.yaml) / [`ihp_sg13g2.md`](pdk/profiles/ihp_sg13g2.md) (https://github.com/IHP-GmbH/IHP-Open-PDK)
  - **SkyWater `SKY130`** — [`pdk/profiles/sky130.yaml`](pdk/profiles/sky130.yaml) / [`sky130.md`](pdk/profiles/sky130.md) (https://github.com/google/skywater-pdk)
- **デフォルト稼働中 PoC PDK**: OpenSUSI **TR-1um**（`1.0 µm` CMOS, 2 層メタル `M1`/`M2`, `5.0 V`, 16 ピン `OSS_FRAME_GIO` — アダプタプロファイル: [`pdk/profiles/tr1um.yaml`](pdk/profiles/tr1um.yaml)、**1 リポジトリ = 実装目標 PDK 1 つ**の Submodule 運用ルールは [`pdk/README.md`](pdk/README.md) を参照）

---

## 1. リポジトリ構成とガバナンスポリシー

OpenSUSI × Google AI 支援チップ設計プラットフォーム標準のディレクトリ構成です。

```text
NEW-130E_MPW_template/
├── README.md                 # 英語版ドキュメント
├── README-JP.md              # 日本語版ドキュメント（本ファイル）
├── AGENTS.md                 # AI エージェント共通契約 (Prefix / 固定)
├── GEMINI.md                 # Gemini / Vertex AI 専用インストラクション (Prefix / 固定)
├── design.yaml               # プロジェクト・PDK・PPA 目標・CI 統合設定 (Prefix スキーマ固定)
├── pdk/                      # 実装目標 PDK 1 つ (Git Submodule) + 分離アダプタプロファイル
│   ├── README.md             # 単一 PDK ポリシー & Git Submodule 切り替え手順
│   ├── profiles/             # テンプレート管理 PDK アダプタ定義 (tr1um, ihp_sg13g2, sky130, new130e)
│   └── tr1um/                # デフォルト PDK Git Submodule (OpenSUSI/TR-1um @ dev)
├── rtl/
│   └── top.v                 # 合成可能 RTL（PoC: 4-bit Registered ALU/Accumulator）
├── constraints/
│   ├── timing.sdc            # SDC タイミング制約
│   └── pin_order.cfg         # パッドフレーム／信号ピン割り当て
├── verification/
│   └── testbench/
│       └── tb_top.v          # 自己チェック付き RTL・ゲートレベルテストベンチ
├── flow/
│   ├── common.sh             # 共通設定・ツール検出
│   ├── synth.sh              # Stage 1: 検証 + RTL Sim + Yosys 合成 + Gate-Level Sim
│   ├── floorplan.sh          # Stage 2: フロアプラン + 配置 + TAP/Decap 挿入
│   ├── place_route.sh        # Stage 3: OpenROAD GRT/DRT + フルチップ GDSII + LVS SPICE 生成
│   ├── signoff.sh            # Stage 4: Precheck + DRC + Strict LVS + MDP/IP62 + STA
│   └── run_all.sh            # GitHub-to-Silicon 一気通貫パイプライン
├── scripts/
│   ├── config_loader.py      # 依存なしの YAML & pin_order.cfg ローダ
│   ├── validate.py           # テンプレート規約・スキーマ・ピン整合・サインオフゲート検証
│   ├── package.py            # MPW Submission Gateway 提出バンドル & SHA-256 マニフェスト生成
│   ├── pre_check.py          # KLayout MPW GDSII Precheck（トップセル・DBU・外形・フレーム）
│   ├── tr1um_place.py        # TR-1um 汎用 TAP2 配置 & FILL3/FILL2 デキャップフィラー
│   ├── tr1um_def2gds.py      # TR-1um DEF → フルチップ GDSII & OSS_FRAME 配線
│   ├── tr1um_v2spice.py      # TR-1um Verilog + DEF → LVS SPICE (.cir) 生成
│   ├── openroad_def2gds.py   # 汎用 openroad_std DEF → GDSII 変換（IHP-130 / SKY130 / NEW-130E）
│   ├── openroad_v2spice.py   # 汎用 openroad_std Verilog → LVS SPICE 生成
│   └── prepare_sky130.py     # google/skywater-pdk サブモジュール向け統合ビュー生成ヘルパ
├── .github/
│   ├── actions/              # 再利用可能アクション (checkout-pdk, setup-klayout)
│   └── workflows/
│       └── design-ci.yml     # CI/CD + GCP Cloud Batch 連携 + MPW サインオフ (Prefix / 固定)
├── docs/
│   ├── design-spec.md        # 設計者が記述する目標仕様書（Gemini への一次入力）
│   └── ai-design-guide.md    # AI 支援チップ設計ワークフローガイド
├── reference/                # 設計チップ向け参考資料（論文・データシート・仕様書・図面等）
└── output/                   # GCP / CI 管理出力先 (Prefix / 固定)
    ├── gds/
    ├── reports/
    └── logs/
```

### ガバナンスポリシー

| 項目 | ポリシー |
| :--- | :--- |
| フォルダ構成 | **Prefix（固定）** |
| `GEMINI.md` / `AGENTS.md` | **Prefix（固定）** |
| `design.yaml` | **Prefix（スキーマ固定・値のみ編集可）** |
| `.github/` | **Prefix（固定）** |
| `output/` | **Prefix（GCP / CI 管理）** |

---

## 2. クイックスタート（TR-1um PoC）

### 前提ツール（ローカル実行時）
> Docker コンテナ（`OpenSUSI-EDA-Container`）を使用する場合はローカルへの個別インストール不要です。

- `python3`（標準ライブラリのみ、外部 `pip` パッケージ不要）
- `iverilog` / `vvp`
- `yosys`
- `openroad`
- `klayout`（`0.30.13` 推奨。Linux の `PATH` および macOS `/Applications/klayout.app` を自動検出）

### フルパイプライン実行
```bash
bash flow/run_all.sh
```

個別ステージごとに実行する場合:
```bash
python3 scripts/validate.py --stage pre
bash flow/synth.sh
bash flow/floorplan.sh
bash flow/place_route.sh
bash flow/signoff.sh
python3 scripts/validate.py --stage post
python3 scripts/package.py
```

### 主な出力成果物
- `output/gds/<top_cell>.gds` — サインオフ済みフルチップ GDSII（TR-1um では `2500 × 2500 µm` `OSS_FRAME_GIO`）
- `output/gds/<top_cell>.cir` — 階層 LVS 参照 SPICE ネットリスト
- `output/gds/<mdp_file>` — MDP / IP62 マスクデータ準備済み GDSII
- `output/reports/summary.json` — CI および Gemini 向けの統合 PPA・サインオフ結果 JSON
- `output/package/<top_cell>_mpw_bundle.tar.gz` — MPW 提出用バンドル + `manifest.json`

---

## 3. 設計者ワークフローと Gemini への指令方法

### 3.1 テンプレートの Clone と事前準備

1. **Submodule を含めて Clone する**:
   ```bash
   git clone --recurse-submodules <YOUR_REPO_URL>
   ```
   *(デフォルトの `tr1um` から `ihp_sg13g2`・`sky130`・`new130e` へ切り替える場合は [`pdk/README.md`](pdk/README.md) に従い、1 リポジトリにつき **実装目標 PDK を 1 つだけ** 設定してください。)*

2. **設計者側の入力ファイルを編集・配置する**:
   - [`design.yaml`](design.yaml): `project`（設計名・`github_user`）、`design.top_cell`、使用する `pdk`、PPA 目標（`targets`）の **値のみ** 更新します（スキーマキーは削除しないこと）。
   - [`docs/design-spec.md`](docs/design-spec.md): 設計したい回路の機能仕様、ピン配置、受け入れ条件を記述します（日本語・英語どちらでも可）。
   - [`reference/`](reference/README.md): *(任意)* 参考論文、データシート、ブロック図、プロトコル仕様、期待値ベクタなどの参考資料を配置します。

### 3.2 Gemini / Antigravity への伝え方（パターン A / B / C）

このリポジトリを開くと、Gemini / Antigravity は [`AGENTS.md`](AGENTS.md) と [`GEMINI.md`](GEMINI.md) を自動的に読み込みます。そのため、EDA フローの手順や DRC/LVS ルール、編集禁止ルールを毎回プロンプトに書く必要はありません。

- **パターン A — `docs/design-spec.md` を書いてから一気に実装・サインオフさせる（基本）**:
  > `docs/design-spec.md` と `reference/` の資料をもとに、現在の PDK 向けに `rtl/top.v`・`constraints/pin_order.cfg`・`constraints/timing.sdc`・`verification/testbench/tb_top.v` を実装し、`flow/run_all.sh` で全ゲート（RTL/GL Sim・P&R・Precheck・DRC・LVS・STA）が PASS するまで仕上げてください。

- **パターン B — 仕様検討から Gemini と相談して始める**:
  > `reference/` に入れた資料をもとに、現在の PDK 制約（ピン数・セル数上限）に収まる回路仕様を `docs/design-spec.md` にドラフトしてください。合意できたら RTL 実装とサインオフ検証に進みます。

- **パターン C — PPA 改善・デバッグの反復**:
  > `output/reports/summary.json` を確認し、クリティカルパスをパイプライン化して Fmax を 20 MHz 以上（またはセル数を目標値以下）に改善したうえで、再度全ゲート PASS させてください。
