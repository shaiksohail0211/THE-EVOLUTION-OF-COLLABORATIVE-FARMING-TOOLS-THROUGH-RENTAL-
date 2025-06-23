# Farm Tools Rental Platform

A web application that allows farmers to rent and sell agricultural tools and equipment. This platform connects farmers who own agricultural tools with those who need them, making farming more efficient and cost-effective.

## Features

- User registration and authentication
- Tool listing with detailed specifications
- Tool rental and purchase requests
- Image upload for tools
- Email notifications for requests and updates
- Responsive design for all devices
- Search and filter tools by category
- Tool maintenance tracking

## Tool Categories

- Tractors
- Harvesters
- Plows
- Seeders
- Irrigation Equipment
- Sprayers
- Cultivators
- Mowers
- Other Agricultural Tools

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/farm-tools-rental.git
cd farm-tools-rental
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the root directory with the following variables:
```
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///toolrental.db
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-email-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

5. Initialize the database:
```bash
python app.py
```

## Usage

1. Start the development server:
```bash
python app.py
```

2. Open your web browser and navigate to `http://localhost:5000`

3. Register a new account or log in with existing credentials

4. Start listing your tools or browsing available tools

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Flask web framework
- Bootstrap for the UI components
- Font Awesome for icons
- All contributors and users of the platform 