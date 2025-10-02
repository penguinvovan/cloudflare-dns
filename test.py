#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функциональности DNS Failover
"""

import sys
import os
import yaml
import requests
import socket
from dns_failover import CloudflareAPI, ServerMonitor


def test_cloudflare_connection(config):
    """Тестирование подключения к Cloudflare API"""
    print("🔍 Тестирование подключения к Cloudflare API...")
    
    try:
        cf_config = config['cloudflare']
        api = CloudflareAPI(cf_config['api_token'], cf_config['zone_id'])
        
        # Попробовать получить DNS запись
        record = api.get_dns_record(cf_config['domain_name'], config['dns']['record_type'])
        
        if record:
            print(f"✅ Cloudflare API работает")
            print(f"   Текущая DNS запись: {record['name']} -> {record['content']}")
            print(f"   TTL: {record['ttl']} секунд")
            return True
        else:
            print(f"❌ DNS запись для {cf_config['domain_name']} не найдена")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка подключения к Cloudflare: {e}")
        return False


def test_server_connectivity(config):
    """Тестирование подключения к серверам"""
    print("\n🔍 Тестирование подключения к серверам...")
    
    monitor = ServerMonitor(config['monitoring']['timeout'])
    results = {}
    
    for server_name, server_config in config['servers'].items():
        print(f"\n   Тестирование {server_name} ({server_config['ip']}:{server_config['port']})...")
        
        # TCP тест
        tcp_result = monitor.check_tcp_connection(server_config['ip'], server_config['port'])
        print(f"   {'✅' if tcp_result else '❌'} TCP соединение: {'OK' if tcp_result else 'FAILED'}")
        
        # HTTP тест (если настроен)
        if config['monitoring'].get('check_method') == 'http':
            http_result = monitor.check_http_connection(
                server_config['ip'], 
                server_config['port'],
                config['monitoring'].get('http_check_path', '/')
            )
            print(f"   {'✅' if http_result else '❌'} HTTP проверка: {'OK' if http_result else 'FAILED'}")
            results[server_name] = tcp_result and http_result
        else:
            results[server_name] = tcp_result
    
    return results


def test_dns_update(config, dry_run=True):
    """Тестирование обновления DNS записи"""
    print(f"\n🔍 Тестирование обновления DNS {'(DRY RUN)' if dry_run else ''}...")
    
    try:
        cf_config = config['cloudflare']
        api = CloudflareAPI(cf_config['api_token'], cf_config['zone_id'])
        
        # Получить текущую DNS запись
        record = api.get_dns_record(cf_config['domain_name'], config['dns']['record_type'])
        if not record:
            print("❌ Не удалось получить DNS запись для тестирования")
            return False
        
        current_ip = record['content']
        print(f"   Текущий IP: {current_ip}")
        
        # Найти альтернативный IP из конфигурации
        test_ip = None
        for server_name, server_config in config['servers'].items():
            if server_config['ip'] != current_ip:
                test_ip = server_config['ip']
                break
        
        if not test_ip:
            print("   ⚠️  Нет альтернативного IP для тестирования")
            return True
        
        if dry_run:
            print(f"   ✅ DNS обновление возможно (тестовый IP: {test_ip})")
            print("   💡 Для реального тестирования запустите с параметром --real-test")
            return True
        else:
            print(f"   🔄 Обновление DNS на {test_ip}...")
            
            success = api.update_dns_record(
                record['id'],
                cf_config['domain_name'],
                test_ip,
                config['dns']['record_type'],
                config['dns']['ttl']
            )
            
            if success:
                print(f"   ✅ DNS успешно обновлен на {test_ip}")
                
                # Вернуть обратно
                print(f"   🔄 Восстановление DNS на {current_ip}...")
                restore_success = api.update_dns_record(
                    record['id'],
                    cf_config['domain_name'],
                    current_ip,
                    config['dns']['record_type'],
                    config['dns']['ttl']
                )
                
                if restore_success:
                    print(f"   ✅ DNS восстановлен на {current_ip}")
                else:
                    print(f"   ❌ Ошибка восстановления DNS! Требуется ручное вмешательство!")
                
                return success and restore_success
            else:
                print("   ❌ Ошибка обновления DNS")
                return False
                
    except Exception as e:
        print(f"❌ Ошибка при тестировании DNS: {e}")
        return False


def test_configuration_validation(config_path):
    """Валидация конфигурационного файла"""
    print("🔍 Проверка конфигурации...")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        errors = []
        warnings = []
        
        # Проверка основных секций
        required_sections = ['cloudflare', 'servers', 'monitoring', 'dns']
        for section in required_sections:
            if section not in config:
                errors.append(f"Отсутствует секция '{section}'")
        
        if errors:
            for error in errors:
                print(f"❌ {error}")
            return None
        
        # Проверка Cloudflare настроек
        cf_config = config['cloudflare']
        required_cf_params = ['api_token', 'zone_id', 'domain_name']
        for param in required_cf_params:
            if not cf_config.get(param) or cf_config[param].startswith("YOUR_"):
                errors.append(f"Необходимо настроить cloudflare.{param}")
        
        # Проверка серверов
        if len(config['servers']) < 2:
            errors.append("Необходимо настроить минимум 2 сервера")
        
        # Проверка приоритетов серверов
        priorities = [s['priority'] for s in config['servers'].values()]
        if len(set(priorities)) != len(priorities):
            warnings.append("Обнаружены дублирующиеся приоритеты серверов")
        
        # Проверка интервалов
        if config['monitoring']['check_interval'] < 30:
            warnings.append("Слишком частые проверки могут нагружать серверы")
        
        if config['dns']['ttl'] < 60:
            warnings.append("TTL меньше 60 секунд может не поддерживаться")
        
        # Вывод результатов
        if errors:
            for error in errors:
                print(f"❌ {error}")
            return None
        
        if warnings:
            for warning in warnings:
                print(f"⚠️  {warning}")
        
        print("✅ Конфигурация валидна")
        return config
        
    except Exception as e:
        print(f"❌ Ошибка при чтении конфигурации: {e}")
        return None


def main():
    """Главная функция тестирования"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Тестирование DNS Failover')
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Путь к файлу конфигурации'
    )
    parser.add_argument(
        '--real-test',
        action='store_true',
        help='Выполнить реальное тестирование DNS (будет временно изменен DNS)'
    )
    
    args = parser.parse_args()
    
    print("🚀 Запуск тестирования DNS Failover System")
    print("=" * 50)
    
    # Проверка конфигурации
    config = test_configuration_validation(args.config)
    if not config:
        print("\n❌ Тестирование прервано из-за ошибок конфигурации")
        sys.exit(1)
    
    # Тестирование Cloudflare API
    cf_ok = test_cloudflare_connection(config)
    
    # Тестирование серверов
    server_results = test_server_connectivity(config)
    
    # Тестирование DNS обновления
    dns_ok = test_dns_update(config, dry_run=not args.real_test)
    
    # Итоговый отчет
    print("\n" + "=" * 50)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 50)
    
    print(f"{'✅' if cf_ok else '❌'} Cloudflare API: {'OK' if cf_ok else 'FAILED'}")
    
    print("Серверы:")
    all_servers_ok = True
    for server_name, result in server_results.items():
        print(f"  {'✅' if result else '❌'} {server_name}: {'OK' if result else 'FAILED'}")
        if not result:
            all_servers_ok = False
    
    print(f"{'✅' if dns_ok else '❌'} DNS обновление: {'OK' if dns_ok else 'FAILED'}")
    
    # Общий результат
    all_ok = cf_ok and all_servers_ok and dns_ok
    print(f"\n{'🎉' if all_ok else '⚠️ '} ОБЩИЙ РЕЗУЛЬТАТ: {'ВСЕ ТЕСТЫ ПРОЙДЕНЫ' if all_ok else 'ЕСТЬ ПРОБЛЕМЫ'}")
    
    if all_ok:
        print("\n✅ Система готова к работе!")
        print("💡 Для запуска сервиса используйте: python main.py")
    else:
        print("\n❌ Исправьте найденные проблемы перед запуском сервиса")
    
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()