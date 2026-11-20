# PDK Configuration & Submodule Policy (`pdk/`)

## 1. Single Target PDK Policy（実装目標 PDK は 1 つを選択）

> **IMPORTANT**: 1 つのチップ設計リポジトリには、**実装目標とする PDK を 1 つだけ選択して配置（原則 Git Submodule 運用）**してください。

- 本テンプレートでは **アダプタ分離型（案 B）** を採用しています。
  - **`pdk/profiles/<pdk_name>.yaml`**: テンプレート側が保持する PDK アダプタ定義（上流 PDK リポジトリのディレクトリ構成を変更せずに取り込むためのマッピング定義）。
  - **`pdk/<target_pdk>/`**: 実装目標の PDK 本体（**1 プロセスのみ**を Git Submodule としてマウント。デフォルトでは `https://github.com/OpenSUSI/TR-1um` (`dev`) を `pdk/tr1um/` に Submodule 設定済み）。
- `scripts/validate.py --stage pre` は `pdk/` 直下（`profiles/` を除く）に **複数の PDK ディレクトリが混在していないこと** を自動検証します。

```text
pdk/
├── README.md                 # 本ドキュメント（運用ポリシー & Submodule 手順）
├── profiles/                 # テンプレート管理の PDK アダプタ定義（案 B）
│   ├── tr1um.yaml            # OpenSUSI TR-1um アダプタ（PoC 稼働中）
│   ├── ihp_sg13g2.yaml       # IHP-130 (SG13G2) アダプタ（IHP-Open-PDK）
│   ├── ihp_sg13g2.md         # IHP-130 セットアップ手順
│   ├── sky130.yaml           # SkyWater SKY130 アダプタ（google/skywater-pdk）
│   ├── sky130.md             # SKY130 セットアップ手順
│   ├── new130e.yaml          # NEW-130E 130 nm アダプタ（Scaffold）
│   └── new130e.md            # NEW-130E 統合チェックリスト
└── <target_pdk>/             # 選択した実装目標 PDK 1 つのみをマウント（Git Submodule）
```

---

## 2. Available Adapter Profiles (`pdk/profiles/`)

| Profile | Process | Upstream PDK Repository | Driver | Status | Guide |
| :--- | :--- | :--- | :---: | :---: | :--- |
| [`profiles/tr1um.yaml`](profiles/tr1um.yaml) | OpenSUSI **TR-1um** (1.0 µm CMOS, 2M, 5.0 V) | https://github.com/OpenSUSI/TR-1um | `tr1um_2m` | **Active (PoC)** | Built-in PoC |
| [`profiles/ihp_sg13g2.yaml`](profiles/ihp_sg13g2.yaml) | **IHP SG13G2** (130 nm SiGe BiCMOS, 5M+2TM, 1.2 V) | https://github.com/IHP-GmbH/IHP-Open-PDK | `openroad_std` | **Ready (Submodule)** | [`ihp_sg13g2.md`](profiles/ihp_sg13g2.md) |
| [`profiles/sky130.yaml`](profiles/sky130.yaml) | **SkyWater SKY130** (130 nm CMOS, `sky130_fd_sc_hd`, 5M, 1.8 V) | https://github.com/google/skywater-pdk | `openroad_std` | **Ready (Submodule)** | [`sky130.md`](profiles/sky130.md) |
| [`profiles/new130e.yaml`](profiles/new130e.yaml) | **NEW-130E** (130 nm CMOS, target foundry MPW) | TBD | `openroad_std` | **Scaffold** | [`new130e.md`](profiles/new130e.md) |

---

## 3. Submodule Workflow（実装目標 PDK の切り替え手順）

### 3.1 共通手順（例: IHP-130 または SKY130 への切り替え）

1. **既存のターゲット PDK Submodule（デフォルト: `pdk/tr1um`）を取り外す**（1 リポジトリ = 1 PDK を維持）:
   ```bash
   git submodule deinit -f pdk/tr1um
   git rm -f pdk/tr1um
   rm -rf .git/modules/pdk/tr1um
   ```

2. **実装目標の PDK リポジトリを Git Submodule として 1 つだけ追加する**:
   - **IHP-130 (`ihp_sg13g2`) の場合**:
     ```bash
     git submodule add -b main https://github.com/IHP-GmbH/IHP-Open-PDK.git pdk/ihp_sg13g2
     git submodule update --init --recursive pdk/ihp_sg13g2
     ```
   - **SKY130 (`sky130`) の場合**:
     ```bash
     git submodule add -b main https://github.com/google/skywater-pdk.git pdk/sky130
     git -C pdk/sky130 submodule update --init libraries/sky130_fd_sc_hd/latest
     make -C pdk/sky130 timing
     python3 scripts/prepare_sky130.py
     ```
     （`volare` / `open_pdks` でビルド済みの `sky130A` を使う場合は [`profiles/sky130.md`](profiles/sky130.md) を参照）
   - **NEW-130E (`new130e`) の場合**:
     ```bash
     git submodule add -b <branch_or_tag> <NEW130E_PDK_REPO_URL> pdk/new130e
     ```

3. **[`design.yaml`](../design.yaml) でアクティブ PDK と `top_cell` プレフィックスを指定する**:
   ```yaml
   # IHP-130 の例
   pdk:
     name: "ihp_sg13g2"
     profile: "pdk/profiles/ihp_sg13g2.yaml"
   design:
     top_cell: "sg13g2_<github_user>"
   ```
   ```yaml
   # SKY130 の例
   pdk:
     name: "sky130"
     profile: "pdk/profiles/sky130.yaml"
   design:
     top_cell: "sky130_<github_user>"
   ```

4. **検証・実行する**:
   ```bash
   python3 scripts/validate.py --stage pre
   bash flow/run_all.sh
   ```

### 3.2 Submodule を含む設計リポジトリの Clone / 更新

- 新規 Clone 時:
  ```bash
  git clone --recurse-submodules <DESIGN_REPO_URL>
  ```
- 既存 Clone 後に Submodule を取得・同期する時:
  ```bash
  git submodule update --init --recursive
  ```

### 3.3 GitHub Actions / Private PDK / NDA PDK での動作

- **公開 PDK Submodule (`IHP-Open-PDK`, `skywater-pdk` 等)**: [`.github/workflows/design-ci.yml`](../.github/workflows/design-ci.yml) は `actions/checkout@v4` で `submodules: recursive` を有効にしているため、追加設定なしで自動取得されます。
- **Private PDK Submodule**: リポジトリの GitHub Secrets に `PDK_SUBMODULE_TOKEN`（対象 PDK リポジトリの読み取り権限を持つ PAT 等）を設定すると、CI が自動で Submodule を認証チェックアウトします。
- **NDA / 非公開 PDK（Git に置けない場合）**: GCP Cloud Batch 実行時に `GCS_PDK_URI`（Repository Variable）を指定すると、EDA コンテナ起動時に GCS から `pdk/` へ実行時オーバーレイ展開されます。

---

## 4. PDK Adapter Contract (`pdk/profiles/<name>.yaml`)

Every profile in `pdk/profiles/<name>.yaml` defines:
1. **Technology & Geometry**: node, DBU, metal stack, core site, die/core dimensions, frame cell names.
2. **Synthesis & Placement**: `dont_use_cells`, buffer/tie/tap/endcap/filler cells, pin layers, target density.
3. **Views**: `tech_lef`, `grt_cells_lef`, `drt_cells_lef`, `liberty`, `stdcell_gds`, `stdcell_spice`, `verilog_models`/`primitives_v`, optional `frame_gds`, `klayout_map`/`klayout_lyp`.
4. **Sign-off Decks**: `drc_mode`/`drc_deck`, `lvs_mode`/`lvs_deck`, optional `mdp_deck`/`ip62_deck`.
5. **Padframe Pinout**: Physical pad names, edges, and power pad assignments (or empty for block/macro designs).
