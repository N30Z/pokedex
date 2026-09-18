FROM nginx:1.27-alpine

COPY index.html style.css app.js /usr/share/nginx/html/
COPY templates /etc/nginx/templates

ENV NGINX_ENVSUBST_TEMPLATE_DIR=/etc/nginx/templates
ENV NGINX_ENVSUBST_OUTPUT_DIR=/usr/share/nginx/html
ENV API_BASE_URL=""

EXPOSE 80
