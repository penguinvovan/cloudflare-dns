# Примеры конфигураций для различных сценариев

## config-simple.yaml - Базовая конфигурация для двух серверов
```yaml
cloudflare:
  api_token: "ваш_токен_здесь"
  zone_id: "ваш_zone_id_здесь"
  domain_name: "example.com"

servers:
  primary:
    ip: "203.0.113.10"
    port: 80
    priority: 1
  
  secondary:
    ip: "203.0.113.20"
    port: 80
    priority: 2

monitoring:
  check_interval: 60
  timeout: 10
  failure_threshold: 3
  check_method: "tcp"

dns:
  record_type: "A"
  ttl: 300

logging:
  level: "INFO"
  file: "dns_failover.log"
```

## config-http.yaml - Конфигурация с HTTP проверками
```yaml
cloudflare:
  api_token: "ваш_токен_здесь"
  zone_id: "ваш_zone_id_здесь"
  domain_name: "example.com"

servers:
  primary:
    ip: "203.0.113.10"
    port: 443
    priority: 1
  
  secondary:
    ip: "203.0.113.20"
    port: 443
    priority: 2

monitoring:
  check_interval: 30
  timeout: 15
  failure_threshold: 2
  check_method: "http"
  http_check_path: "/health"

dns:
  record_type: "A"
  ttl: 60

logging:
  level: "DEBUG"
  file: "dns_failover.log"
```

## config-multiple.yaml - Конфигурация с множественными серверами
```yaml
cloudflare:
  api_token: "ваш_токен_здесь"
  zone_id: "ваш_zone_id_здесь"
  domain_name: "example.com"

servers:
  primary_datacenter:
    ip: "203.0.113.10"
    port: 80
    priority: 1
  
  secondary_datacenter:
    ip: "203.0.113.20"
    port: 80
    priority: 2
    
  backup_vps:
    ip: "203.0.113.30"
    port: 80
    priority: 3

monitoring:
  check_interval: 45
  timeout: 8
  failure_threshold: 3
  check_method: "tcp"

dns:
  record_type: "A"
  ttl: 180

logging:
  level: "INFO"
  file: "dns_failover.log"
```

## config-subdomain.yaml - Конфигурация для поддомена
```yaml
cloudflare:
  api_token: "ваш_токен_здесь"
  zone_id: "ваш_zone_id_здесь"
  domain_name: "api.example.com"

servers:
  primary:
    ip: "203.0.113.10"
    port: 8080
    priority: 1
  
  secondary:
    ip: "203.0.113.20"
    port: 8080
    priority: 2

monitoring:
  check_interval: 30
  timeout: 5
  failure_threshold: 2
  check_method: "http"
  http_check_path: "/api/status"

dns:
  record_type: "A"
  ttl: 120

logging:
  level: "INFO"
  file: "api_dns_failover.log"
```

## Примеры использования

### Запуск с разными конфигурациями:

```bash
# Основная конфигурация
python main.py

# Использование специфической конфигурации
python main.py --config config-http.yaml

# Тестирование конфигурации
python test.py --config config-multiple.yaml

# Просмотр статуса
python main.py --status --config config-subdomain.yaml
```

### Настройка для Windows Service:

1. Создайте batch файл `start_dns_failover.bat`:
```batch
@echo off
cd /d "C:\path\to\dns-api"
python main.py --config config.yaml
pause
```

2. Добавьте в автозагрузку или используйте Task Scheduler

### Настройка cron для Linux:

```bash
# Добавить в crontab для запуска при перезагрузке
@reboot cd /path/to/dns-api && python main.py --config config.yaml

# Или создать systemd service (см. README.md)
```