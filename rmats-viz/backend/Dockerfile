FROM python:3.12-slim

WORKDIR /app

# samtools is a SYSTEM dependency of the backend (not a pip package): it is
# used by app/services/sequence.py (`samtools faidx`) for every splice-site /
# hnRNP region extraction from the GRCh38 FASTA.  The FASTA itself is NOT
# downloaded by the application any more — run data/setup_grch38_fasta.sh
# once so that /data/GRCh38.fa(.fai) exists (see README, Quick start).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    samtools \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
