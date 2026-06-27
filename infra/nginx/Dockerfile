FROM certbot/certbot:v3.0.1
COPY init-certs.sh /init-certs.sh
RUN chmod +x /init-certs.sh
ENTRYPOINT ["/init-certs.sh"]
