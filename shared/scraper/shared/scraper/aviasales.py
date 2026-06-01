"""Aviasales.ru flight price scraper using Botasaurus browser automation."""

import re
from datetime import date, datetime
from typing import Any

from botasaurus.browser import Driver, browser


class AviasalesScraper:
    """Scraper for Aviasales.ru flight prices."""

    BASE_URL = "https://www.aviasales.ru"

    @staticmethod
    def build_search_url(origin: str, destination: str, departure_date: date | str) -> str:
        """Build search URL for Aviasales.

        Args:
            origin: Origin airport IATA code.
            destination: Destination airport IATA code.
            departure_date: Date object or string in YYYY-MM-DD format.

        Returns:
            Search URL for the flight route.
        """
        if isinstance(departure_date, date):
            date_str = departure_date.strftime("%d%m")
        else:
            date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
            date_str = date_obj.strftime("%d%m")

        return f"{AviasalesScraper.BASE_URL}/search/{origin}{date_str}{destination}1"

    @browser(
        reuse_driver=True,
        wait_for_complete_page_load=False,
        block_images=True,
        headless=True,
        add_arguments=["--disable-dev-shm-usage", "--disable-gpu"],
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    def scrape_flights(driver: Driver, data: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: N805 — botasaurus @browser инжектит driver первым аргументом
        """Scrape flight prices from Aviasales.ru.

        Args:
            driver: Botasaurus browser driver (injected by decorator).
            data: Dictionary with keys: origin, destination, departure_date.

        Returns:
            List of flight data dictionaries.
        """
        origin = data["origin"]
        destination = data["destination"]
        departure_date = data["departure_date"]

        url = AviasalesScraper.build_search_url(origin, destination, departure_date)
        print(f"Opening page: {url}")

        try:
            driver.get(url, timeout=120)
        except Exception as e:
            print(f"Warning: Error loading page: {e}")
            print("Trying to continue...")

        # Wait for results to load
        driver.sleep(15)

        # Scroll page to load all results
        try:
            for _ in range(3):
                driver.run_js("window.scrollTo(0, document.body.scrollHeight);")
                driver.sleep(1)
        except Exception as e:
            print(f"Warning: Could not scroll page: {e}")

        flights = []

        try:
            # Find flight cards using multiple selectors
            selectors = [
                '[data-test-id^="direct-schedule-group-"]',
                '[data-test-id*="direct-ticket"]',
                '[class*="__XM25TpwN6UmJJLL"]',
                '[data-test-id="flight-card"]',
                ".product-list__item",
                '[class*="snippet"]',
            ]

            flight_cards = []
            for selector in selectors:
                flight_cards = driver.select_all(selector)
                if flight_cards:
                    print(f"Found flight cards: {len(flight_cards)} (selector: {selector})")
                    break

            if not flight_cards:
                print("No flight cards found")
                return []

            for idx, card in enumerate(flight_cards[:20]):
                try:
                    flight_data = AviasalesScraper._parse_flight_card(
                        card, origin, destination, departure_date
                    )
                    if flight_data and flight_data.get("price"):
                        # Convert datetime to string for JSON
                        flight_data_json = flight_data.copy()
                        if "scraped_at" in flight_data_json and isinstance(
                            flight_data_json["scraped_at"], datetime
                        ):
                            flight_data_json["scraped_at"] = flight_data_json[
                                "scraped_at"
                            ].isoformat()

                        # Use string version of date for JSON
                        if "departure_date_str" in flight_data_json:
                            flight_data_json["departure_date"] = flight_data_json[
                                "departure_date_str"
                            ]
                            del flight_data_json["departure_date_str"]

                        flights.append(flight_data_json)
                        print(
                            f"Flight {idx + 1}: {flight_data.get('airline', 'N/A')} - "
                            f"{flight_data['price']} RUB"
                        )
                except Exception as e:
                    print(f"Error parsing flight card {idx + 1}: {e}")
                    continue

        except Exception as e:
            print(f"Error finding flight cards: {e}")

        print(f"Total flights collected: {len(flights)}")
        return flights

    @staticmethod
    def _parse_flight_card(
        card: Any, origin: str, destination: str, departure_date: date | str
    ) -> dict[str, Any] | None:
        """Parse flight information from a card element.

        Args:
            card: Botasaurus element representing a flight card.
            origin: Origin airport IATA code.
            destination: Destination airport IATA code.
            departure_date: Departure date.

        Returns:
            Dictionary with flight data or None if price not found.
        """
        # Convert date for JSON serialization
        if isinstance(departure_date, date):
            departure_date_str = departure_date.isoformat()
        else:
            departure_date_str = departure_date
            departure_date = datetime.strptime(departure_date, "%Y-%m-%d").date()

        flight_data: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,  # Keep date object for DB
            "departure_date_str": departure_date_str,  # Add string for JSON
            "scraped_at": datetime.utcnow(),
        }

        try:
            card_text = card.text

            # Get price - find numbers before currency symbols
            price_match = re.search(r"(\d[\d\s\u202f\xa0]*)\s*[₽руб]", card_text)
            if price_match:
                price_str = (
                    price_match.group(1)
                    .replace(" ", "")
                    .replace("\u202f", "")
                    .replace("\xa0", "")
                    .strip()
                )
                if price_str:
                    flight_data["price"] = float(price_str)
                    flight_data["currency"] = "RUB"

            # Fallback price extraction
            if "price" not in flight_data:
                clean_text = card_text.replace(" ", "").replace("\xa0", "").replace("\u202f", "")
                numbers = re.findall(r"\d{3,}", clean_text)
                if numbers:
                    flight_data["price"] = float(max(numbers, key=lambda x: int(x)))
                    flight_data["currency"] = "RUB"

            # Airline detection
            airlines_keywords = [
                "Аэрофлот",
                "S7",
                "Победа",
                "Уральские авиалинии",
                "Utair",
                "Nordwind",
                "Smartavia",
                "Азимут",
                "Red Wings",
                "Россия",
            ]

            for airline in airlines_keywords:
                if airline.lower() in card_text.lower():
                    flight_data["airline"] = airline
                    break

            if "airline" not in flight_data:
                flight_data["airline"] = "Unknown"

            # Departure and arrival times
            times = re.findall(r"\b(\d{1,2}:\d{2})\b", card_text)
            if len(times) >= 2:
                flight_data["departure_time"] = times[0]
                flight_data["arrival_time"] = times[1]

            # Duration
            duration_match = re.search(r"(\d+\s*ч\s*\d*\s*мин|\d+ч|\d+\s*ч)", card_text)
            if duration_match:
                flight_data["duration"] = duration_match.group(1).strip()

            # Stops
            if "прям" in card_text.lower() or "без пересадок" in card_text.lower():
                flight_data["stops"] = 0
            else:
                stops_match = re.search(r"(\d+)\s*пересад", card_text.lower())
                if stops_match:
                    flight_data["stops"] = int(stops_match.group(1))

        except Exception as e:
            print(f"Error extracting data: {e}")

        return flight_data if "price" in flight_data else None
