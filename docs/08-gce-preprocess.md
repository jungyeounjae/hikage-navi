# GCE에서 東京23区 전처리하기

상태: 확정  
관련: [07-gcp-cicd.md](07-gcp-cicd.md), [설계](superpowers/specs/2026-08-20-gce-preprocess-design.md)

Mac 디스크에 `data/raw`(CityGML ZIP·압축 해제)를 **두지 않는다**.  
전처리는 GCE VM에서 돌리고, 결과는 GCS에 보관한다. VM은 **필요할 때만 start**, 끝나면 **stop**.

Cloud Run API는 기동 시 GCS `processed/tokyo23`만 sync한다. 절차·환경 변수는 [07-gcp-cicd.md](07-gcp-cicd.md).

## 1. 한 번만: GCP 준비

결제 계정이 연결된 프로젝트에서:

```bash
export PROJECT_ID=your-gcp-project
export REGION=asia-northeast1
export ZONE=asia-northeast1-a
export BUCKET=${PROJECT_ID}-data
export INSTANCE=hikage-preprocess

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com storage.googleapis.com

# 버킷 (이미 있으면 생략)
gsutil mb -l "$REGION" "gs://${BUCKET}"

# VM (200GB, e2-standard-4) — 이미 hikage-preprocess 가 있으면 생략
gcloud compute instances create "$INSTANCE" \
  --zone="$ZONE" \
  --machine-type=e2-standard-4 \
  --boot-disk-size=200GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --scopes=cloud-platform

# 생성 직후 중지해 두면 디스크만 과금
gcloud compute instances stop "$INSTANCE" --zone="$ZONE"
```

로컬 셸에 기본값을 넣으려면 (선택):

```bash
export HIKAGE_GCP_PROJECT="$PROJECT_ID"
export HIKAGE_GCE_ZONE="$ZONE"
export HIKAGE_GCE_INSTANCE="$INSTANCE"
export HIKAGE_GCS_BUCKET="gs://${BUCKET}"
```

## 2. VM 최초 세팅 (SSH 한 번)

```bash
gcloud compute instances start "$INSTANCE" --zone="$ZONE"
gcloud compute ssh "$INSTANCE" --zone="$ZONE"
```

VM 안에서:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git
# gcloud / gsutil 은 이미지에 있으면 스킵. 없으면 Google Cloud SDK 설치

git clone https://github.com/jungyeounjae/hikage-navi.git
cd hikage-navi
python3 -m venv api/.venv
. api/.venv/bin/activate
pip install -e "api/[preprocess]"
```

끝나면 `exit` 후 Mac에서:

```bash
./scripts/gce-preprocess-stop.sh
```

## 3. 전처리 사이클 (매회)

Mac에서:

```bash
./scripts/gce-preprocess-start.sh
gcloud compute ssh "$INSTANCE" --zone="$ZONE"
```

VM에서:

```bash
cd ~/hikage-navi   # 또는 clone 경로
git pull
. api/.venv/bin/activate
export HIKAGE_ROOT="$PWD"
# 전체 23구 (수 시간). 먼저 시부야만이면 --wards 13113
python api/scripts/preprocess.py --wards all
```

끝나면 Mac에서 GCS로 올리기:

```bash
./scripts/gce-preprocess-sync-up.sh
./scripts/gce-preprocess-stop.sh
```

`sync-up`은 VM의 `data/raw`와 `data/processed/tokyo23`을 버킷으로 `rsync`한다.

## 4. Mac: raw 없이 쓰기

**권장:** Mac에서 `data/raw`를 삭제한다 (이미 gitignore).

로컬 API만 돌릴 때 processed만 받기:

```bash
./scripts/gce-preprocess-sync-down.sh
export HIKAGE_DATA_DIR="$PWD/data/processed/tokyo23"
cd api && . .venv/bin/activate && uvicorn hikage_navi.app:app --port 8000
```

ZIP·citygml 해제본은 받지 않는다.

## 5. 비용 메모

- **중지된 VM**: 부트 디스크(200GB) 스토리지만 과금
- **가동 중**: vCPU·메모리·디스크
- **GCS**: raw+processed 용량에 따른 저장 요금 (저렴한 편)
- 전처리가 끝나면 반드시 `stop`할 것

## 6. 헬퍼 스크립트

| 스크립트 | 역할 |
| --- | --- |
| `scripts/gce-preprocess-start.sh` | VM start |
| `scripts/gce-preprocess-stop.sh` | VM stop |
| `scripts/gce-preprocess-sync-up.sh` | VM → GCS (`raw`, `tokyo23`) |
| `scripts/gce-preprocess-sync-down.sh` | GCS → Mac (`tokyo23`만) |

환경 변수 기본값: `HIKAGE_GCP_PROJECT`, `HIKAGE_GCE_ZONE`, `HIKAGE_GCE_INSTANCE`, `HIKAGE_GCS_BUCKET`.

## 7. 아직 하지 않는 것

Cloud Run이 GCS에서 직접 구별 건물을 읽는 연동은 배포 2차.  
지금은 전처리·보관만 GCE/GCS로 옮긴다.
