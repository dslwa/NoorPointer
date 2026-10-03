FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY app.js styles.css favicon.svg /usr/share/nginx/html/

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
