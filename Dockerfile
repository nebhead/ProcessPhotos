FROM python:3.13-slim

WORKDIR /

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

COPY install/requirements.txt .
COPY install/postproc.sh /
COPY install/preproc.sh /
COPY install/entrypoint.sh /

RUN chmod +x /postproc.sh
RUN chmod +x /preproc.sh
RUN chmod +x /entrypoint.sh

RUN pip install --no-cache-dir -r requirements.txt

COPY /common /common/
COPY /exif /exif/
COPY /static /static/
COPY /templates /templates/
COPY /sortphotos /sortphotos
COPY /immich /immich
COPY app.py app.py
COPY versions.json versions.json

# Create data directories
RUN mkdir -p /import /export /config /originals /static/img/import /logs && \
	chown -R appuser:appgroup /import && \
	chown -R appuser:appgroup /export && \
	chown -R appuser:appgroup /config && \
	chown -R appuser:appgroup /originals && \
	chown -R appuser:appgroup /static/img && \
	chown -R appuser:appgroup /logs && \
	chmod -R 775 /config && \
	chmod -R 775 /export && \
	chmod -R 775 /import && \
	chmod -R 775 /originals && \
	chmod -R 775 /static/img && \
	chmod -R 775 /logs 

# Create symlinks
RUN rm -rf /static/img/import && ln -s /import /static/img/import

USER appuser

EXPOSE 5000

ENTRYPOINT [ "/entrypoint.sh" ]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
