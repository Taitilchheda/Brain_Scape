FROM python:3.11-slim

# System dependencies for neuroimaging
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install FSL (skull stripping, MCFLIRT, FNIRT)
RUN echo "deb http://neuro.debian.net/debian data main contrib non-free" >> /etc/apt/sources.list \
    && echo "deb http://neuro.debian.net/debian focal main contrib non-free" >> /etc/apt/sources.list \
    && apt-key adv --recv-keys --keyserver hkp://keyserver.ubuntu.com:80 0xA5D32F012649A5A9 \
    && apt-get update \
    && apt-get install -y fsl-core \
    && rm -rf /var/lib/apt/lists/*

ENV FSLDIR=/usr/share/fsl
ENV PATH=$FSLDIR/bin:$PATH

# Install ANTs
RUN wget -q https://github.com/ANTsX/ANTs/releases/download/v2.5.0/ants-2.5.0-linux_x86_64.tar.gz \
    && tar -xzf ants-2.5.0-linux_x86_64.tar.gz -C /opt \
    && rm ants-2.5.0-linux_x86_64.tar.gz

ENV ANTSPATH=/opt/ants-2.5.0/
ENV PATH=$ANTSPATH:$PATH

# Copy requirements and install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Download atlas files
RUN mkdir -p data/atlases data/raw data/processed data/registered data/samples

# Expose API port
EXPOSE 8000

# Default: run API server
CMD ["uvicorn", "mlops.serve.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]