import requests
from bs4 import BeautifulSoup
import csv
import os
import time
import random
from urllib.parse import urljoin, urlparse
import json
from typing import Dict, List, Optional
import re
from dataclasses import dataclass, asdict


@dataclass
class BookInfo:
    """Data class to store book information"""
    title: str = ""
    price_current: str = ""
    price_original: str = ""
    discount: str = ""
    publisher: str = ""
    language: str = ""
    binding: str = ""
    publication_date: str = ""
    isbn: str = ""
    pages: str = ""
    height: str = ""
    width: str = ""
    thickness: str = ""
    product_code: str = ""
    availability: str = ""
    rating: str = ""
    reviews_count: str = ""
    description: str = ""
    main_image_url: str = ""
    additional_images: List[str] = None
    local_image_path: str = ""
    book_url: str = ""

    def __post_init__(self):
        if self.additional_images is None:
            self.additional_images = []


class FlipBooksScraper:
    def __init__(self, base_url: str = "https://www.flip.kz"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def get_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page with retry logic"""
        for attempt in range(retries):
            try:
                print(f"Fetching: {url} (attempt {attempt + 1})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(2, 5))
                else:
                    print(f"Failed to fetch {url} after {retries} attempts")
                    return None
        return None

    def download_image(self, image_url: str, save_path: str) -> bool:
        """Download an image from URL to local path"""
        try:
            if not image_url:
                return False
                
            # Handle relative URLs
            if image_url.startswith('//'):
                image_url = 'https:' + image_url
            elif image_url.startswith('/'):
                image_url = self.base_url + image_url
            elif not image_url.startswith('http'):
                image_url = self.base_url + '/' + image_url.lstrip('/')
            
            print(f"Downloading image: {image_url}")
            response = self.session.get(image_url, timeout=30)
            response.raise_for_status()
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            print(f"Image saved: {save_path}")
            return True
            
        except Exception as e:
            print(f"Error downloading image {image_url}: {e}")
            return False

    def extract_book_info_from_catalog(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Extract basic book info from catalog page"""
        book_data = []
        
        # Method 1: Look for images with product URLs (most reliable for Flip.kz)
        img_elements = soup.find_all('img', src=re.compile(r'prod/\d+.*\.(jpg|png|webp)'))
        
        for img in img_elements:
            try:
                book_info = {
                    'image_url': img.get('src'),
                    'title': img.get('alt', '').strip(),
                }
                
                # Find the parent link to get book URL
                link_parent = img.find_parent('a')
                if link_parent and link_parent.get('href'):
                    href = link_parent.get('href')
                    if 'catalog?prod=' in href or 'item' in href:
                        book_info['book_url'] = urljoin(self.base_url, href)
                
                # Find container with price and other info
                # Look for price in various parent containers
                containers_to_check = []
                current = img.parent
                depth = 0
                while current and depth < 5:  # Check up to 5 levels up
                    containers_to_check.append(current)
                    current = current.parent
                    depth += 1
                
                for container in containers_to_check:
                    if not container:
                        continue
                        
                    container_text = container.get_text()
                    
                    # Extract prices
                    price_matches = re.findall(r'(\d+(?:\s*\d+)*)\s*₸', container_text)
                    if price_matches:
                        # Clean prices (remove spaces within numbers)
                        prices = [price.replace(' ', '') for price in price_matches]
                        # Remove duplicates and sort
                        unique_prices = sorted(set(prices), key=lambda x: int(x))
                        
                        if len(unique_prices) >= 2:
                            book_info['price_current'] = unique_prices[0] + ' ₸'
                            book_info['price_original'] = unique_prices[-1] + ' ₸'
                            # Calculate discount
                            try:
                                current_price = int(unique_prices[0])
                                original_price = int(unique_prices[-1])
                                if original_price > current_price:
                                    discount = round((1 - current_price / original_price) * 100)
                                    book_info['discount'] = f"-{discount}%"
                            except:
                                pass
                        elif len(unique_prices) == 1:
                            book_info['price_current'] = unique_prices[0] + ' ₸'
                    
                    # Extract availability
                    if 'На складе' in container_text:
                        book_info['availability'] = 'На складе'
                    elif 'Завтра' in container_text:
                        book_info['availability'] = 'Завтра'
                    elif 'июня' in container_text or 'июля' in container_text:
                        # Extract specific date
                        date_match = re.search(r'(\d+)\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', container_text)
                        if date_match:
                            book_info['availability'] = date_match.group(0)
                    
                    # Try to extract title if not found in alt text
                    if not book_info.get('title'):
                        # Look for text that could be a title
                        lines = [line.strip() for line in container_text.split('\n') if line.strip()]
                        for line in lines:
                            # Skip prices, availability, and other metadata
                            if (len(line) > 10 and 
                                not re.match(r'^\d+\s*₸', line) and 
                                'На складе' not in line and 
                                'Завтра' not in line and
                                not re.match(r'^-?\d+%', line) and
                                'мягкая обложка' not in line and
                                'твердый переплет' not in line and
                                not re.match(r'^\d{4}$', line)):  # Not just a year
                                
                                book_info['title'] = line
                                break
                    
                    # Extract binding type
                    if 'мягкая обложка' in container_text:
                        book_info['binding'] = 'мягкая обложка'
                    elif 'твердый переплет' in container_text:
                        book_info['binding'] = 'твердый переплет'
                    
                    # If we found some info, break out of container loop
                    if book_info.get('price_current') or book_info.get('availability'):
                        break
                
                # Only add if we have meaningful data
                if book_info.get('image_url') or book_info.get('title') or book_info.get('book_url'):
                    book_data.append(book_info)
                    
            except Exception as e:
                print(f"Error extracting book info: {e}")
                continue
        
        # Method 2: Alternative approach - look for product containers
        if not book_data:
            product_containers = soup.find_all(['div', 'article', 'section'], class_=re.compile(r'product|item|book|card'))
            
            for container in product_containers:
                try:
                    book_info = {}
                    
                    # Find image
                    img = container.find('img', src=True)
                    if img:
                        book_info['image_url'] = img.get('src')
                        book_info['title'] = img.get('alt', '').strip()
                    
                    # Find link
                    link = container.find('a', href=True)
                    if link:
                        book_info['book_url'] = urljoin(self.base_url, link.get('href'))
                    
                    # Extract other info from container text
                    container_text = container.get_text()
                    
                    # Extract prices
                    price_matches = re.findall(r'(\d+(?:\s*\d+)*)\s*₸', container_text)
                    if price_matches:
                        prices = [price.replace(' ', '') for price in price_matches]
                        unique_prices = sorted(set(prices), key=lambda x: int(x))
                        
                        if len(unique_prices) >= 2:
                            book_info['price_current'] = unique_prices[0] + ' ₸'
                            book_info['price_original'] = unique_prices[-1] + ' ₸'
                        elif len(unique_prices) == 1:
                            book_info['price_current'] = unique_prices[0] + ' ₸'
                    
                    if book_info:
                        book_data.append(book_info)
                        
                except Exception as e:
                    print(f"Error in alternative extraction: {e}")
                    continue
        
        return book_data

    def extract_detailed_book_info(self, book_url: str) -> BookInfo:
        """Extract detailed information from individual book page"""
        soup = self.get_page(book_url)
        if not soup:
            return BookInfo(book_url=book_url)
        
        book = BookInfo(book_url=book_url)
        
        try:
            # Extract title
            title_selectors = ['h1', '.title', '[class*="title"]', '[class*="name"]']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    book.title = title_elem.get_text().strip()
                    break
            
            # Extract description - Enhanced to find book descriptions
            description_found = False
            
            # Method 1: Look for specific description patterns
            page_text = soup.get_text()
            
            # Find long paragraphs that look like book descriptions
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text().strip()
                # Look for substantial text that might be a description
                if (len(text) > 200 and 
                    not re.match(r'^\d+\s*₸', text) and  # Not just price
                    'Цена:' not in text and
                    'ISBN' not in text and
                    'Издательство' not in text and
                    'Количество страниц' not in text):
                    book.description = text
                    description_found = True
                    break
            
            # Method 2: Look for description in div elements
            if not description_found:
                desc_selectors = [
                    '.description', '[class*="description"]', 
                    '.content', '[class*="content"]',
                    '.summary', '[class*="summary"]',
                    '.about', '[class*="about"]',
                    '.details', '[class*="details"]'
                ]
                
                for selector in desc_selectors:
                    elements = soup.select(selector)
                    for elem in elements:
                        text = elem.get_text().strip()
                        if len(text) > 100:  # Likely description
                            book.description = text
                            description_found = True
                            break
                    if description_found:
                        break
            
            # Method 3: Look for text blocks similar to your example
            if not description_found:
                # Look for text that contains typical book description patterns
                text_blocks = soup.find_all(['div', 'span', 'p'], string=re.compile(r'.{200,}'))
                for block in text_blocks:
                    text = block.get_text().strip()
                    # Check if it looks like a book description
                    if (len(text) > 200 and
                        ('книга' in text.lower() or 'автор' in text.lower() or 
                         'глава' in text.lower() or 'история' in text.lower() or
                         'читатель' in text.lower() or 'произведение' in text.lower())):
                        book.description = text
                        description_found = True
                        break
            
            # Extract main image
            img_selectors = ['img[src*="prod/"]', '.main-image img', '.product-image img', 'img']
            for selector in img_selectors:
                img = soup.select_one(selector)
                if img and img.get('src'):
                    src = img.get('src')
                    if 'prod/' in src:
                        book.main_image_url = src
                        break
            
            # Extract additional images
            all_images = soup.find_all('img', src=True)
            for img in all_images:
                src = img.get('src')
                if src and 'prod/' in src and src != book.main_image_url:
                    book.additional_images.append(src)
            
            # Extract prices with enhanced regex
            text = soup.get_text()
            
            # Look for crossed out prices and current prices
            price_current_match = re.search(r'(?:Цена со скидкой:|Цена:)\s*(?:\*\*)?(\d+(?:\s*\d+)*)\s*₸', text)
            if price_current_match:
                book.price_current = price_current_match.group(1).replace(' ', '') + ' ₸'
            
            price_original_match = re.search(r'~~(\d+(?:\s*\d+)*)\s*₸~~', text)
            if price_original_match:
                book.price_original = price_original_match.group(1).replace(' ', '') + ' ₸'
            
            # Extract discount percentage
            discount_match = re.search(r'\*\*(-\d+%)\*\*', text)
            if discount_match:
                book.discount = discount_match.group(1)
            
            # Fallback: general price extraction
            if not book.price_current:
                price_matches = re.findall(r'(\d+(?:\s*\d+)*)\s*₸', text)
                if price_matches:
                    prices = [price.replace(' ', '') for price in price_matches]
                    prices = sorted(set(prices), key=lambda x: int(x))
                    if len(prices) >= 2:
                        book.price_current = prices[0] + ' ₸'
                        book.price_original = prices[-1] + ' ₸'
                    elif len(prices) == 1:
                        book.price_current = prices[0] + ' ₸'
            
            # Extract detailed information from the page text
            # Look for patterns like "Издательство: ...", "Язык: ...", etc.
            info_patterns = {
                'publisher': r'Издательство[:\s]+([^\n,]+)',
                'language': r'Язык[:\s]+([^\n,]+)',
                'binding': r'(?:Переплет|Обложка)[:\s]+([^\n,]+)',
                'publication_date': r'(?:Дата выхода|Год издания)[:\s]+([^\n,]+)',
                'isbn': r'ISBN[:\s]+([^\n,\s]+)',
                'pages': r'(?:Количество страниц|Страниц)[:\s]+([^\n,]+)',
                'height': r'Высота издания[:\s]+([^\n,]+)',
                'width': r'Ширина издания[:\s]+([^\n,]+)',
                'thickness': r'Толщина издания[:\s]+([^\n,]+)',
                'product_code': r'Код товара[:\s]+([^\n,]+)',
            }
            
            for field, pattern in info_patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    setattr(book, field, match.group(1).strip())
            
            # Extract availability
            if 'На складе' in text:
                book.availability = 'На складе'
            elif 'Завтра' in text:
                book.availability = 'Завтра'
            elif re.search(r'\d+\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', text):
                date_match = re.search(r'(\d+\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря))', text)
                if date_match:
                    book.availability = date_match.group(1)
            
            # Extract rating and reviews
            rating_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:из\s*5|★|⭐)', text)
            if rating_match:
                book.rating = rating_match.group(1)
            
            reviews_match = re.search(r'(\d+)\s*отзыв', text)
            if reviews_match:
                book.reviews_count = reviews_match.group(1)
            elif 'Нет отзывов' in text:
                book.reviews_count = '0'
            
            # Extract author from title or description if present
            if book.title and not book.publisher:
                # Sometimes author is in the title
                author_match = re.search(r'^(.+?)\s+[-–—]\s+(.+)$', book.title)
                if author_match:
                    potential_author = author_match.group(2)
                    if len(potential_author.split()) <= 3:  # Likely an author name
                        book.publisher = potential_author
            
        except Exception as e:
            print(f"Error extracting detailed info from {book_url}: {e}")
        
        return book

    def run_scraper(self, catalog_url: str, output_dir: str, max_pages: int = 10, csv_output_path: str = None) -> Dict:
        """Main scraper function"""
        print(f"Starting Flip.kz books scraper")
        print(f"Catalog URL: {catalog_url}")
        print(f"Output directory: {output_dir}")
        print(f"Max pages: {max_pages}")
        
        # Create output directories
        os.makedirs(output_dir, exist_ok=True)
        images_dir = os.path.join(output_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)
        
        all_books = []
        successful_downloads = 0
        failed_downloads = 0
        
        # Process pages
        for page_num in range(1, max_pages + 1):
            page_url = f"{catalog_url}&page={page_num}" if '?' in catalog_url else f"{catalog_url}?page={page_num}"
            
            print(f"\n--- Processing page {page_num} ---")
            soup = self.get_page(page_url)
            
            if not soup:
                print(f"Failed to fetch page {page_num}")
                continue
            
            # Extract basic book info from catalog
            catalog_books = self.extract_book_info_from_catalog(soup, page_url)
            print(f"Found {len(catalog_books)} books on page {page_num}")
            
            # Process each book
            for i, catalog_book in enumerate(catalog_books, 1):
                print(f"\nProcessing book {i}/{len(catalog_books)} on page {page_num}")
                
                # Get detailed information if we have a book URL
                if catalog_book.get('book_url'):
                    detailed_book = self.extract_detailed_book_info(catalog_book['book_url'])
                else:
                    detailed_book = BookInfo()
                    detailed_book.book_url = page_url
                
                # Merge catalog info with detailed info
                if not detailed_book.title and catalog_book.get('title'):
                    detailed_book.title = catalog_book['title']
                if not detailed_book.main_image_url and catalog_book.get('image_url'):
                    detailed_book.main_image_url = catalog_book['image_url']
                if not detailed_book.price_current and catalog_book.get('price_current'):
                    detailed_book.price_current = catalog_book['price_current']
                if not detailed_book.price_original and catalog_book.get('price_original'):
                    detailed_book.price_original = catalog_book['price_original']
                if not detailed_book.discount and catalog_book.get('discount'):
                    detailed_book.discount = catalog_book['discount']
                if not detailed_book.availability and catalog_book.get('availability'):
                    detailed_book.availability = catalog_book['availability']
                if not detailed_book.binding and catalog_book.get('binding'):
                    detailed_book.binding = catalog_book['binding']
                
                # Download main image
                if detailed_book.main_image_url:
                    # Create safe filename
                    safe_title = re.sub(r'[^\w\s-]', '', detailed_book.title or f'book_{len(all_books)}')
                    safe_title = re.sub(r'[-\s]+', '_', safe_title)[:50]
                    
                    image_extension = '.jpg'
                    if detailed_book.main_image_url:
                        parsed_url = urlparse(detailed_book.main_image_url)
                        if parsed_url.path:
                            image_extension = os.path.splitext(parsed_url.path)[1] or '.jpg'
                    
                    image_filename = f"{safe_title}_{len(all_books)}{image_extension}"
                    image_path = os.path.join(images_dir, image_filename)
                    
                    if self.download_image(detailed_book.main_image_url, image_path):
                        detailed_book.local_image_path = image_path
                        successful_downloads += 1
                    else:
                        failed_downloads += 1
                
                all_books.append(detailed_book)
                
                # Add delay between requests
                time.sleep(random.uniform(1, 3))
            
            # Add delay between pages
            time.sleep(random.uniform(2, 5))
            
            # Break if no books found (end of catalog)
            if not catalog_books:
                print(f"No books found on page {page_num}, stopping")
                break
        
        # Save to CSV
        if csv_output_path:
            self.save_to_csv(all_books, csv_output_path)
        
        # Save to JSON as backup
        json_path = os.path.join(output_dir, 'books_data.json')
        self.save_to_json(all_books, json_path)
        
        result = {
            'dataset': all_books,
            'csv_file': csv_output_path,
            'json_file': json_path,
            'output_dir': output_dir,
            'images_dir': images_dir,
            'total_books': len(all_books),
            'successful_image_downloads': successful_downloads,
            'failed_image_downloads': failed_downloads,
        }
        
        return result

    def save_to_csv(self, books: List[BookInfo], csv_path: str):
        """Save books data to CSV file"""
        print(f"\nSaving {len(books)} books to CSV: {csv_path}")
        
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            if not books:
                return
            
            # Get all field names
            fieldnames = list(asdict(books[0]).keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for book in books:
                book_dict = asdict(book)
                # Convert list to string for CSV
                book_dict['additional_images'] = '; '.join(book.additional_images)
                writer.writerow(book_dict)
        
        print(f"CSV saved successfully: {csv_path}")

    def save_to_json(self, books: List[BookInfo], json_path: str):
        """Save books data to JSON file"""
        print(f"\nSaving {len(books)} books to JSON: {json_path}")
        
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        
        books_data = [asdict(book) for book in books]
        
        with open(json_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(books_data, jsonfile, ensure_ascii=False, indent=2)
        
        print(f"JSON saved successfully: {json_path}")


def run_flip_scraper(catalog_url: str, output_dir: str, max_pages: int = 10, csv_output_path: str = None) -> Dict:
    """Convenience function to run the scraper"""
    scraper = FlipBooksScraper()
    return scraper.run_scraper(catalog_url, output_dir, max_pages, csv_output_path)


if __name__ == "__main__":
    result = run_flip_scraper(
        catalog_url="https://www.flip.kz/catalog?subsection=134",  
        output_dir=r"C:\Users\User\Desktop\flip_book\data\fantasy",
        max_pages=50,  
        csv_output_path=r"C:\Users\User\Desktop\flip_book\data\fantasy\flip_books_fantasy.csv"
    )
    
    print(f"\n=== SCRAPING COMPLETED ===")
    print(f"Total books collected: {result['total_books']}")
    print(f"Successful image downloads: {result['successful_image_downloads']}")
    print(f"Failed image downloads: {result['failed_image_downloads']}")
    print(f"Data saved to CSV: {result['csv_file']}")
    print(f"Data saved to JSON: {result['json_file']}")
    print(f"Images saved in: {result['images_dir']}")
    
    # Print sample of collected data
    if result['dataset']:
        print(f"\n=== SAMPLE BOOK DATA ===")
        sample_book = result['dataset'][0]
        print(f"Title: {sample_book.title}")
        print(f"Price: {sample_book.price_current}")
        print(f"Publisher: {sample_book.publisher}")
        print(f"Description: {sample_book.description[:200]}..." if sample_book.description else "No description")
        print(f"Image URL: {sample_book.main_image_url}")
        print(f"Local Image: {sample_book.local_image_path}")