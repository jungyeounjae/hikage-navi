# hikage-navi (日陰ナビ)

[한국어](README.md) | **日本語**

渋谷区を歩く人向けの、**日陰ルート案内**パイロットです。

韓国の[그늘로](https://ttubeok.com/)を参考にしていますが、公共交通・車窓の日当たり・街路樹は入れません。  
渋谷区内で出発地と到着地を指定すると、**最短の徒歩ルート**と**日陰が多い徒歩ルート**を比べられます。

仕様は確定済みで、**API コア（地理・太陽・影・グラフ・経路）**の実装が進んでいます。Web UI・実データの前処理は以降のタスクです。

## v0.1 でやること

- 渋谷区の地図に、時刻ごとの建物の影を表示する
- 地図をタップして出発・到着を指定する
- 最短ルートと日陰ルートを比較する（距離・時間・日陰%）
- 夜間は最短ルートのみ

## やらないこと

鉄道・バス、車窓の推薦、街路樹、地下街、場所検索、ネイティブアプリ、ログイン。

## 技術

| 層 | 選択 |
| --- | --- |
| Web | TypeScript, React, Vite, MapLibre |
| API | Python, FastAPI |
| Web の公開 | Vercel |
| API の公開 | Cloud Build → Artifact Registry → Cloud Run |

開発はノート PC 上で行います。Docker・GCP・Vercel は、アプリがローカルで動いてからつなぎます。

## 仕様

実装は次の文書に従います（本文は한국어です）。

| 文書 | 内容 |
| --- | --- |
| [docs/01-requirements.md](docs/01-requirements.md) | 要件定義 |
| [docs/02-functional-spec.md](docs/02-functional-spec.md) | 機能仕様 |
| [docs/03-ui-spec.md](docs/03-ui-spec.md) | 画面仕様 |
| [docs/04-data-algorithm.md](docs/04-data-algorithm.md) | データ・アルゴリズム |
| [docs/05-acceptance.md](docs/05-acceptance.md) | 受け入れ基準 |
| [docs/06-tech-stack.md](docs/06-tech-stack.md) | 技術選定 |
| [docs/07-gcp-cicd.md](docs/07-gcp-cicd.md) | Vercel / GCP CI/CD |

## データの出典

- 地図: [国土地理院](https://maps.gsi.go.jp/development/ichiran.html)
- 建物: [Project PLATEAU](https://www.mlit.go.jp/plateau/)（渋谷区）
- 道路: [OpenStreetMap](https://www.openstreetmap.org/copyright)

v0.1 の採用・保留（ほこナビDP、街路樹、Cool Share など）は [docs/04-data-algorithm.md](docs/04-data-algorithm.md) §1.6 を参照。

## 進捗

- [x] 要件・機能仕様
- [x] API コア（タスク 1–5: geo・sun・shadows・graph・routing）
- [ ] FastAPI サービス・Web UI・実データ（タスク 6–10）
- [ ] Docker（API）
- [ ] Cloud Run + Artifact Registry
- [ ] Vercel
