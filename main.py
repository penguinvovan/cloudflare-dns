#!/usr/bin/env python3
"""
DNS Failover Service
Автоматическое переключение DNS записей в Cloudflare при недоступности серверов
"""

import os
import sys
import yaml
import logging
import schedule
import time
import signal
import json
from datetime import datetime
from typing import Dict, Any

from dns_failover import DNSFailover


class DNSFailoverService:
    """Основной сервис для запуска DNS failover"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = None
        self.dns_failover = None
        self.running = False
        self.logger = None
        
        # Настройка обработчиков сигналов для корректного завершения
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        print(f"\nПолучен сигнал {signum}. Завершение работы...")
        self.stop()
    
    def load_config(self) -> bool:
        """Загрузить конфигурацию из файла"""
        try:
            if not os.path.exists(self.config_path):
                print(f"Файл конфигурации {self.config_path} не найден!")
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # Валидация основных параметров
            required_sections = ['cloudflare', 'servers', 'monitoring', 'dns']
            for section in required_sections:
                if section not in self.config:
                    print(f"Отсутствует обязательная секция '{section}' в конфигурации!")
                    return False
            
            # Проверка Cloudflare настроек
            cf_config = self.config['cloudflare']
            required_cf_params = ['api_token', 'zone_id', 'domain_name']
            for param in required_cf_params:
                if not cf_config.get(param) or cf_config[param] == f"YOUR_{param.upper()}":
                    print(f"Необходимо настроить параметр cloudflare.{param} в config.yaml!")
                    return False
            
            # Проверка серверов
            if len(self.config['servers']) < 2:
                print("Необходимо настроить минимум 2 сервера!")
                return False
            
            print("Конфигурация успешно загружена")
            return True
            
        except Exception as e:
            print(f"Ошибка при загрузке конфигурации: {e}")
            return False
    
    def setup_logging(self):
        """Настроить логирование"""
        try:
            log_config = self.config.get('logging', {})
            log_level = getattr(logging, log_config.get('level', 'INFO').upper())
            log_file = log_config.get('file', 'dns_failover.log')
            
            # Создание форматтера
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # Настройка root logger
            logger = logging.getLogger()
            logger.setLevel(log_level)
            
            # Очистка существующих обработчиков
            logger.handlers.clear()
            
            # Консольный обработчик
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # Файловый обработчик
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            self.logger = logger
            self.logger.info("Логирование настроено")
            
        except Exception as e:
            print(f"Ошибка при настройке логирования: {e}")
            sys.exit(1)
    
    def initialize_failover(self) -> bool:
        """Инициализировать DNS failover"""
        try:
            self.dns_failover = DNSFailover(self.config)
            self.logger.info("DNS Failover инициализирован")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации DNS Failover: {e}")
            return False
    
    def run_check(self):
        """Запустить проверку и переключение"""
        try:
            self.logger.debug("Запуск проверки серверов...")
            self.dns_failover.check_and_failover()
            
        except Exception as e:
            self.logger.error(f"Ошибка при выполнении проверки: {e}")
    
    def print_status(self):
        """Вывести текущий статус"""
        try:
            status = self.dns_failover.get_status()
            
            print("\n" + "="*60)
            print(f"DNS Failover Status - {status['timestamp']}")
            print("="*60)
            print(f"Активный сервер: {status['current_active_server']}")
            print("\nСтатус серверов:")
            
            for server_name, server_info in status['servers'].items():
                status_icon = "✅" if server_info['healthy'] else "❌"
                active_mark = " [АКТИВНЫЙ]" if server_name == status['current_active_server'] else ""
                
                print(f"  {status_icon} {server_name}{active_mark}")
                print(f"     IP: {server_info['ip']}:{server_info['port']}")
                print(f"     Приоритет: {server_info['priority']}")
                print(f"     Ошибок подряд: {server_info['failure_count']}")
            
            print("="*60)
            
        except Exception as e:
            self.logger.error(f"Ошибка при выводе статуса: {e}")
    
    def start(self):
        """Запустить сервис"""
        print("Запуск DNS Failover Service...")
        
        # Загрузка конфигурации
        if not self.load_config():
            sys.exit(1)
        
        # Настройка логирования
        self.setup_logging()
        
        # Инициализация failover
        if not self.initialize_failover():
            sys.exit(1)
        
        # Первоначальная проверка
        self.logger.info("Выполнение первоначальной проверки...")
        self.run_check()
        self.print_status()
        
        # Настройка расписания
        check_interval = self.config['monitoring']['check_interval']
        schedule.every(check_interval).seconds.do(self.run_check)
        
        # Расписание для вывода статуса каждые 5 минут
        schedule.every(5).minutes.do(self.print_status)
        
        self.logger.info(f"Сервис запущен. Интервал проверки: {check_interval} секунд")
        self.running = True
        
        # Основной цикл
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал прерывания")
        
        finally:
            self.stop()
    
    def stop(self):
        """Остановить сервис"""
        self.running = False
        if self.logger:
            self.logger.info("DNS Failover Service остановлен")
        print("Сервис остановлен")


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='DNS Failover Service')
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Путь к файлу конфигурации (по умолчанию: config.yaml)'
    )
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='Выполнить тестовую проверку и показать статус'
    )
    parser.add_argument(
        '--status', '-s',
        action='store_true',
        help='Показать текущий статус и выйти'
    )
    
    args = parser.parse_args()
    
    service = DNSFailoverService(args.config)
    
    if args.test or args.status:
        # Тестовый режим
        if not service.load_config():
            sys.exit(1)
        
        service.setup_logging()
        
        if not service.initialize_failover():
            sys.exit(1)
        
        if args.test:
            print("Выполнение тестовой проверки...")
            service.run_check()
        
        service.print_status()
        
    else:
        # Запуск сервиса
        service.start()


if __name__ == "__main__":
    main()