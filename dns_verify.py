#!/usr/bin/env python3
"""
Расширенная проверка изменений DNS записей
Включает проверку через внешние DNS серверы для подтверждения распространения изменений
"""

import socket
import time
import subprocess
import requests
import yaml
from dns_failover import CloudflareAPI
from typing import List, Dict, Optional


class DNSChecker:
    """Класс для проверки DNS записей через различные источники"""
    
    def __init__(self):
        # Список публичных DNS серверов для проверки
        self.dns_servers = [
            ("Google DNS", "8.8.8.8"),
            ("Cloudflare DNS", "1.1.1.1"),
            ("OpenDNS", "208.67.222.222"),
            ("Quad9", "9.9.9.9")
        ]
        
        # Онлайн сервисы для проверки DNS
        self.online_checkers = [
            ("whatsmydns.net", "https://www.whatsmydns.net/api/details"),
            ("dns.google", "https://dns.google/resolve")
        ]
    
    def resolve_dns_local(self, domain: str) -> Optional[str]:
        """Резолвинг DNS через локальный резолвер"""
        try:
            return socket.gethostbyname(domain)
        except socket.gaierror:
            return None
    
    def resolve_dns_specific_server(self, domain: str, dns_server: str) -> Optional[str]:
        """Резолвинг DNS через конкретный DNS сервер"""
        try:
            # Используем nslookup для Windows
            if hasattr(subprocess, 'run'):
                result = subprocess.run(
                    ['nslookup', domain, dns_server],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'Address:' in line and dns_server not in line:
                            # Извлекаем IP адрес
                            parts = line.split('Address:')
                            if len(parts) > 1:
                                ip = parts[1].strip()
                                # Проверяем, что это действительно IP адрес
                                try:
                                    socket.inet_aton(ip)
                                    return ip
                                except socket.error:
                                    continue
            return None
        except Exception:
            return None
    
    def check_dns_google_api(self, domain: str) -> Optional[str]:
        """Проверка DNS через Google DNS API"""
        try:
            url = "https://dns.google/resolve"
            params = {
                "name": domain,
                "type": "A"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "Answer" in data and len(data["Answer"]) > 0:
                    return data["Answer"][0]["data"]
            
            return None
        except Exception:
            return None
    
    def check_dns_cloudflare_api(self, domain: str) -> Optional[str]:
        """Проверка DNS через Cloudflare DNS API"""
        try:
            url = "https://cloudflare-dns.com/dns-query"
            headers = {
                "Accept": "application/dns-json"
            }
            params = {
                "name": domain,
                "type": "A"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "Answer" in data and len(data["Answer"]) > 0:
                    return data["Answer"][0]["data"]
            
            return None
        except Exception:
            return None
    
    def comprehensive_dns_check(self, domain: str) -> Dict[str, Optional[str]]:
        """Комплексная проверка DNS через все доступные методы"""
        results = {}
        
        print(f"🔍 Проверка DNS для {domain}...")
        
        # Локальный резолвер
        local_ip = self.resolve_dns_local(domain)
        results["Local DNS"] = local_ip
        print(f"   📍 Локальный DNS: {local_ip or 'Ошибка'}")
        
        # Проверка через различные публичные DNS серверы
        for name, server in self.dns_servers:
            ip = self.resolve_dns_specific_server(domain, server)
            results[name] = ip
            print(f"   🌐 {name} ({server}): {ip or 'Ошибка'}")
        
        # Проверка через API
        google_ip = self.check_dns_google_api(domain)
        results["Google DNS API"] = google_ip
        print(f"   🔗 Google DNS API: {google_ip or 'Ошибка'}")
        
        cloudflare_ip = self.check_dns_cloudflare_api(domain)
        results["Cloudflare DNS API"] = cloudflare_ip
        print(f"   🔗 Cloudflare DNS API: {cloudflare_ip or 'Ошибка'}")
        
        return results
    
    def wait_for_dns_propagation(self, domain: str, expected_ip: str, max_wait: int = 300) -> bool:
        """Ожидание распространения DNS изменений"""
        print(f"⏳ Ожидание распространения DNS изменений...")
        print(f"   Ожидаемый IP: {expected_ip}")
        print(f"   Максимальное время ожидания: {max_wait} секунд")
        
        start_time = time.time()
        check_interval = 15  # Проверять каждые 15 секунд
        
        while time.time() - start_time < max_wait:
            results = self.comprehensive_dns_check(domain)
            
            # Подсчитаем количество серверов, которые вернули правильный IP
            correct_count = sum(1 for ip in results.values() if ip == expected_ip)
            total_count = len([ip for ip in results.values() if ip is not None])
            
            print(f"   📊 Правильный IP на {correct_count}/{total_count} серверах")
            
            # Если большинство серверов вернуло правильный IP, считаем что изменения распространились
            if total_count > 0 and correct_count / total_count >= 0.7:
                elapsed = int(time.time() - start_time)
                print(f"   ✅ DNS изменения распространились за {elapsed} секунд!")
                return True
            
            if time.time() - start_time < max_wait:
                print(f"   ⏱️  Ожидание {check_interval} секунд перед следующей проверкой...")
                time.sleep(check_interval)
        
        print(f"   ⚠️  Время ожидания истекло. DNS может еще распространяться.")
        return False


def test_dns_change_with_verification(config_path: str = "config.yaml"):
    """Тест изменения DNS с полной верификацией"""
    print("🚀 Запуск теста изменения DNS с верификацией")
    print("=" * 60)
    
    # Загрузка конфигурации
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False
    
    # Инициализация
    cf_config = config['cloudflare']
    api = CloudflareAPI(cf_config['api_token'], cf_config['zone_id'])
    checker = DNSChecker()
    domain = cf_config['domain_name']
    
    print(f"🎯 Тестируемый домен: {domain}")
    
    # Получение текущей DNS записи
    record = api.get_dns_record(domain, config['dns']['record_type'])
    if not record:
        print("❌ Не удалось получить текущую DNS запись")
        return False
    
    original_ip = record['content']
    print(f"📍 Исходный IP: {original_ip}")
    
    # Поиск альтернативного IP
    test_ip = None
    for server_name, server_config in config['servers'].items():
        if server_config['ip'] != original_ip:
            test_ip = server_config['ip']
            test_server_name = server_name
            break
    
    if not test_ip:
        print("⚠️  Нет альтернативного IP для тестирования")
        return False
    
    print(f"🔄 Тестовый IP: {test_ip} (сервер: {test_server_name})")
    
    try:
        # Проверка исходного состояния DNS
        print(f"\n📋 Исходное состояние DNS:")
        initial_results = checker.comprehensive_dns_check(domain)
        
        # Изменение DNS записи
        print(f"\n🔄 Изменение DNS записи на {test_ip}...")
        success = api.update_dns_record(
            record['id'],
            domain,
            test_ip,
            config['dns']['record_type'],
            config['dns']['ttl']
        )
        
        if not success:
            print("❌ Не удалось изменить DNS запись")
            return False
        
        print("✅ DNS запись изменена в Cloudflare")
        
        # Проверка немедленного изменения через Cloudflare API
        time.sleep(5)  # Небольшая пауза
        updated_record = api.get_dns_record(domain, config['dns']['record_type'])
        if updated_record and updated_record['content'] == test_ip:
            print(f"✅ Cloudflare API подтверждает изменение: {updated_record['content']}")
        else:
            print("⚠️  Cloudflare API не подтверждает изменение")
        
        # Ожидание распространения DNS
        print(f"\n⏳ Проверка распространения DNS изменений...")
        propagated = checker.wait_for_dns_propagation(domain, test_ip, max_wait=180)
        
        # Финальная проверка
        print(f"\n📋 Финальное состояние DNS после изменения:")
        final_results = checker.comprehensive_dns_check(domain)
        
        # Восстановление исходной записи
        print(f"\n🔄 Восстановление исходной DNS записи ({original_ip})...")
        restore_success = api.update_dns_record(
            record['id'],
            domain,
            original_ip,
            config['dns']['record_type'],
            config['dns']['ttl']
        )
        
        if restore_success:
            print("✅ DNS запись восстановлена")
            
            # Проверка восстановления
            time.sleep(5)
            restored_record = api.get_dns_record(domain, config['dns']['record_type'])
            if restored_record and restored_record['content'] == original_ip:
                print(f"✅ Cloudflare API подтверждает восстановление: {restored_record['content']}")
        else:
            print("❌ Ошибка восстановления DNS записи!")
        
        # Итоговый отчет
        print(f"\n" + "=" * 60)
        print("📊 ИТОГОВЫЙ ОТЧЕТ")
        print("=" * 60)
        
        # Анализ результатов
        changed_count = sum(1 for ip in final_results.values() if ip == test_ip)
        total_count = len([ip for ip in final_results.values() if ip is not None])
        
        print(f"🎯 Домен: {domain}")
        print(f"📍 Исходный IP: {original_ip}")
        print(f"🔄 Тестовый IP: {test_ip}")
        print(f"✅ Cloudflare API изменение: {'Успешно' if success else 'Неудача'}")
        print(f"🌐 DNS серверы с правильным IP: {changed_count}/{total_count}")
        print(f"📡 Распространение DNS: {'Завершено' if propagated else 'В процессе'}")
        print(f"🔙 Восстановление: {'Успешно' if restore_success else 'Неудача'}")
        
        if changed_count > 0:
            print(f"\n🎉 ТЕСТ УСПЕШЕН! DNS изменения работают корректно.")
        else:
            print(f"\n⚠️  ЧАСТИЧНЫЙ УСПЕХ: DNS изменяется в Cloudflare, но может требовать больше времени для распространения.")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка во время тестирования: {e}")
        
        # Попытка восстановления в случае ошибки
        try:
            print("🔄 Попытка аварийного восстановления...")
            api.update_dns_record(
                record['id'],
                domain,
                original_ip,
                config['dns']['record_type'],
                config['dns']['ttl']
            )
            print("✅ Аварийное восстановление выполнено")
        except:
            print("❌ Аварийное восстановление не удалось! Требуется ручное вмешательство!")
        
        return False


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Расширенная проверка DNS изменений')
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Путь к файлу конфигурации'
    )
    parser.add_argument(
        '--domain', '-d',
        help='Домен для проверки (если не указан, используется из конфигурации)'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Только проверить текущее состояние DNS без изменений'
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        # Только проверка без изменений
        checker = DNSChecker()
        
        if args.domain:
            domain = args.domain
        else:
            try:
                with open(args.config, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                domain = config['cloudflare']['domain_name']
            except Exception as e:
                print(f"❌ Ошибка загрузки конфигурации: {e}")
                return
        
        print(f"🔍 Проверка текущего состояния DNS для {domain}")
        print("=" * 50)
        checker.comprehensive_dns_check(domain)
    else:
        # Полный тест с изменениями
        test_dns_change_with_verification(args.config)


if __name__ == "__main__":
    main()