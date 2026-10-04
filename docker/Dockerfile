# Free Flying Forecast: WRF + WPS (built from source) and the Python pipeline, for Linux arm64.
# UNVERIFIED: written without a Docker daemon available. Build and fix on the iMac (task T012).
FROM ubuntu:24.04 AS wrf-build

ARG WRF_VERSION=4.6.1
ARG WPS_VERSION=4.6.0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran m4 csh perl tcsh curl ca-certificates file \
    libnetcdf-dev libnetcdff-dev libopenmpi-dev openmpi-bin \
    libpng-dev zlib1g-dev libjpeg-dev \
    && apt-get clean

ENV NETCDF=/usr WRFIO_NCD_LARGE_FILE_SUPPORT=1 WRF_EM_CORE=1 WRF_CHEM=0
WORKDIR /opt

# WRF: pick the GNU gfortran/gcc "dmpar" option by parsing configure's menu (numbers differ
# between architectures), with basic nesting.
RUN curl -fsSL https://github.com/wrf-model/WRF/releases/download/v${WRF_VERSION}/v${WRF_VERSION}.tar.gz \
      | tar xz && mv WRF-${WRF_VERSION} WRF \
 && cd WRF \
 && MENU="$(./configure </dev/null 2>&1 || true)" \
 && N="$(echo "$MENU" | grep 'GNU (gfortran/gcc)' | grep -oE '[0-9]+\. +\(dmpar\)' | head -1 | grep -oE '^[0-9]+')" \
 && echo "WRF configure option: $N" && test -n "$N" \
 && printf '%s\n1\n' "$N" | ./configure \
 && ./compile -j 4 em_real > compile.log 2>&1 \
 && test -x main/wrf.exe -a -x main/real.exe

# WPS needs WRF built first. Serial build; GRIB2 via PNG/zlib (GFS does not use JPEG2000).
RUN curl -fsSL https://github.com/wrf-model/WPS/archive/refs/tags/v${WPS_VERSION}.tar.gz \
      | tar xz && mv WPS-${WPS_VERSION} WPS \
 && cd WPS \
 && MENU="$(./configure </dev/null 2>&1 || true)" \
 && N="$(echo "$MENU" | grep -i 'gfortran' | grep -iE 'serial' | grep -iv 'no_grib2' | head -1 | grep -oE '^ *[0-9]+' | tr -d ' ')" \
 && echo "WPS configure option: $N" && test -n "$N" \
 && printf '%s\n' "$N" | ./configure \
 && ./compile > compile.log 2>&1 \
 && test -x geogrid.exe -a -x ungrib.exe -a -x metgrid.exe

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnetcdf19t64 libnetcdff7 libopenmpi3t64 openmpi-bin libgfortran5 libpng16-16t64 \
    git openssh-client ca-certificates curl tcsh \
    && apt-get clean
COPY --from=wrf-build /opt/WRF /opt/WRF
COPY --from=wrf-build /opt/WPS /opt/WPS
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV WRF_DIR=/opt/WRF WPS_DIR=/opt/WPS UV_PROJECT_ENVIRONMENT=/opt/venv OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY config ./config
COPY templates ./templates
COPY docker/namelists ./docker/namelists
RUN uv sync --frozen --no-dev
ENV PATH=/opt/venv/bin:$PATH
ENTRYPOINT ["ffforecast"]
CMD ["--help"]
