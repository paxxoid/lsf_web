
#!/bin/sh

set -e

echo "Waiting for MariaDB..."

#until mariadb-admin ping \
#    --host="${DB_HOST}" \
#    --port="${DB_PORT}" \
#    --user="${DB_USER}" \
#    --password="${DB_PASSWORD}" \
#    --silent
#do
#    sleep 2
#done

echo "MariaDB is ready."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    --access-logformat '%({x-real-ip}i)s - - [%(t)s] "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" forwarded-for="%({x-forwarded-for}i)s" proxy="%(h)s"'

