# Aigent Type Standards - Religious Level Type Checking

This document demonstrates the strict typing and documentation standards enforced by `scripts/strict_type_check.sh`.

## Example of Properly Typed Code

```python
"""Module for handling user authentication.

This module provides secure authentication mechanisms including
password hashing, token generation, and session management.
"""

from typing import Dict, List, Optional, Tuple, Union, Any, Protocol, TypeVar, Final
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import asyncio


# Type aliases for clarity
UserId = str
Token = str
HashedPassword = str
SessionData = Dict[str, Any]

# Constants with type annotations
MAX_LOGIN_ATTEMPTS: Final[int] = 5
TOKEN_EXPIRY_SECONDS: Final[int] = 3600


@dataclass
class User:
    """Represents a user in the system.

    Attributes:
        id: Unique identifier for the user.
        username: User's chosen username.
        email: User's email address.
        created_at: Timestamp of account creation.
    """

    id: UserId
    username: str
    email: str
    created_at: datetime


class AuthenticationError(Exception):
    """Raised when authentication fails.

    Args:
        message: Error message describing the failure.
        attempts_remaining: Number of login attempts left.
    """

    def __init__(self, message: str, attempts_remaining: int) -> None:
        """Initialize the authentication error.

        Args:
            message: Error message to display.
            attempts_remaining: Number of attempts remaining.
        """
        super().__init__(message)
        self.attempts_remaining: int = attempts_remaining


class Authenticator:
    """Handles user authentication and session management.

    This class provides methods for user login, logout, and session
    validation with secure password handling.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize the authenticator with configuration.

        Args:
            config_path: Path to the configuration file.

        Raises:
            ValueError: If config_path does not exist.
            IOError: If config file cannot be read.
        """
        if not config_path.exists():
            raise ValueError(f"Config file not found: {config_path}")

        self._config_path: Path = config_path
        self._sessions: Dict[UserId, SessionData] = {}
        self._login_attempts: Dict[str, int] = {}

    async def authenticate(
        self,
        username: str,
        password: str,
        remember_me: bool = False
    ) -> Tuple[User, Token]:
        """Authenticate a user with username and password.

        Args:
            username: The user's username.
            password: The user's password (will be hashed).
            remember_me: Whether to create a persistent session.

        Returns:
            A tuple containing the authenticated user and session token.

        Raises:
            AuthenticationError: If authentication fails.
            ValueError: If username or password is empty.
            ConnectionError: If database is unreachable.
        """
        if not username or not password:
            raise ValueError("Username and password required")

        # Check login attempts
        attempts: int = self._login_attempts.get(username, 0)
        if attempts >= MAX_LOGIN_ATTEMPTS:
            raise AuthenticationError(
                "Too many login attempts",
                attempts_remaining=0
            )

        # Authenticate logic here
        user: User = await self._verify_credentials(username, password)
        token: Token = await self._generate_token(user.id, persistent=remember_me)

        # Reset attempts on success
        self._login_attempts[username] = 0

        return user, token

    async def _verify_credentials(self, username: str, password: str) -> User:
        """Verify user credentials against database.

        Args:
            username: Username to verify.
            password: Password to verify.

        Returns:
            The authenticated user object.

        Raises:
            AuthenticationError: If credentials are invalid.
        """
        # Implementation would go here
        hashed: HashedPassword = self._hash_password(password)
        # ... database lookup ...

        return User(
            id="user123",
            username=username,
            email=f"{username}@example.com",
            created_at=datetime.now()
        )

    def _hash_password(self, password: str) -> HashedPassword:
        """Hash a password using secure algorithm.

        Args:
            password: Plain text password to hash.

        Returns:
            The hashed password string.
        """
        # Use proper hashing library in production
        return HashedPassword(f"hashed_{password}")

    async def _generate_token(
        self,
        user_id: UserId,
        persistent: bool = False
    ) -> Token:
        """Generate a session token for the user.

        Args:
            user_id: ID of the user to generate token for.
            persistent: Whether token should persist across sessions.

        Returns:
            The generated session token.
        """
        import secrets
        token: Token = Token(secrets.token_urlsafe(32))

        self._sessions[user_id] = {
            "token": token,
            "created_at": datetime.now(),
            "persistent": persistent
        }

        return token

    def logout(self, user_id: UserId) -> None:
        """Log out a user and invalidate their session.

        Args:
            user_id: ID of the user to log out.
        """
        self._sessions.pop(user_id, None)

    def is_authenticated(self, user_id: UserId, token: Token) -> bool:
        """Check if a user session is valid.

        Args:
            user_id: ID of the user to check.
            token: Session token to validate.

        Returns:
            True if the session is valid, False otherwise.
        """
        session: Optional[SessionData] = self._sessions.get(user_id)
        if session is None:
            return False

        return session["token"] == token


# Example of a Protocol for dependency injection
class StorageProtocol(Protocol):
    """Protocol for storage implementations.

    Any class implementing this protocol can be used
    as a storage backend for the authentication system.
    """

    async def get_user(self, user_id: UserId) -> Optional[User]:
        """Retrieve a user by ID.

        Args:
            user_id: The user's unique identifier.

        Returns:
            The user object if found, None otherwise.
        """
        ...

    async def save_user(self, user: User) -> None:
        """Save a user to storage.

        Args:
            user: The user object to save.

        Raises:
            IOError: If the save operation fails.
        """
        ...


# Generic type variable for flexibility
T = TypeVar('T', bound='BaseModel')


class BaseModel:
    """Base class for all data models.

    Provides common functionality for serialization
    and validation.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary representation.

        Returns:
            Dictionary containing all model fields.
        """
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls: type[T], data: Dict[str, Any]) -> T:
        """Create model instance from dictionary.

        Args:
            data: Dictionary containing model fields.

        Returns:
            New instance of the model.

        Raises:
            ValueError: If required fields are missing.
        """
        return cls(**data)


# Example async function with proper typing
async def process_login_queue(
    queue: asyncio.Queue[Tuple[str, str]],
    authenticator: Authenticator
) -> List[Tuple[User, Token]]:
    """Process queued login requests.

    Args:
        queue: Queue containing username/password pairs.
        authenticator: Authenticator instance to use.

    Returns:
        List of successfully authenticated users with tokens.
    """
    results: List[Tuple[User, Token]] = []

    while not queue.empty():
        username, password = await queue.get()
        try:
            result: Tuple[User, Token] = await authenticator.authenticate(
                username,
                password
            )
            results.append(result)
        except AuthenticationError:
            # Log failed attempt
            pass

    return results
```

## Key Requirements

### 1. **Every Function Must Have Type Hints**
```python
# BAD - No type hints
def add(x, y):
    return x + y

# GOOD - Complete type hints
def add(x: int, y: int) -> int:
    return x + y
```

### 2. **Every Function Must Have a Docstring**
```python
# BAD - No docstring
def calculate_tax(amount: float, rate: float) -> float:
    return amount * rate

# GOOD - Complete Google-style docstring
def calculate_tax(amount: float, rate: float) -> float:
    """Calculate tax on a given amount.

    Args:
        amount: The base amount to tax.
        rate: The tax rate as a decimal (e.g., 0.15 for 15%).

    Returns:
        The calculated tax amount.

    Raises:
        ValueError: If amount is negative or rate is not between 0 and 1.
    """
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    if not 0 <= rate <= 1:
        raise ValueError("Rate must be between 0 and 1")
    return amount * rate
```

### 3. **Use Specific Types, Not Generic Ones**
```python
from typing import List, Dict, Optional, Union, Tuple

# BAD - Too generic
def process_data(data: list) -> dict:
    pass

# GOOD - Specific types
def process_data(data: List[str]) -> Dict[str, int]:
    pass

# BETTER - Type aliases for complex types
JsonDict = Dict[str, Union[str, int, float, bool, None]]
def process_json(data: JsonDict) -> JsonDict:
    pass
```

### 4. **No Implicit Optional**
```python
# BAD - Implicit optional
def greet(name: str = None) -> str:
    pass

# GOOD - Explicit optional
def greet(name: Optional[str] = None) -> str:
    pass
```

### 5. **Type Class Attributes**
```python
# BAD - No type hints on class attributes
class Config:
    def __init__(self):
        self.host = "localhost"
        self.port = 8080

# GOOD - Type hints on all attributes
class Config:
    host: str
    port: int

    def __init__(self) -> None:
        self.host = "localhost"
        self.port = 8080
```

### 6. **Use Protocols for Duck Typing**
```python
from typing import Protocol

class Drawable(Protocol):
    """Protocol for objects that can be drawn."""

    def draw(self, canvas: Canvas) -> None:
        """Draw the object on a canvas."""
        ...

# Any class with a draw method matching this signature
# will satisfy the protocol
```

### 7. **Type Async Functions**
```python
# BAD - Missing async types
async def fetch_data(url):
    pass

# GOOD - Complete async typing
async def fetch_data(url: str) -> Dict[str, Any]:
    """Fetch data from URL.

    Args:
        url: The URL to fetch from.

    Returns:
        The fetched data as a dictionary.

    Raises:
        HTTPError: If the fetch fails.
    """
    pass
```

### 8. **Use Final for Constants**
```python
from typing import Final

# BAD - Mutable constant
MAX_SIZE = 100

# GOOD - Immutable constant with type
MAX_SIZE: Final[int] = 100
```

### 9. **Type Decorators**
```python
from typing import Callable, TypeVar
from functools import wraps

F = TypeVar('F', bound=Callable[..., Any])

def retry(attempts: int = 3) -> Callable[[F], F]:
    """Retry a function on failure.

    Args:
        attempts: Number of retry attempts.

    Returns:
        The decorated function.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Implementation
            pass
        return wrapper  # type: ignore
    return decorator
```

## Running the Type Checker

```bash
# Run all checks
./scripts/strict_type_check.sh

# Auto-fix formatting and imports
./scripts/strict_type_check.sh --fix

# Verbose output for debugging
./scripts/strict_type_check.sh -v

# Check only, no fixes
./scripts/strict_type_check.sh --check-only
```

## Common Type Checking Errors and Fixes

| Error | Fix |
|-------|-----|
| `Missing return statement` | Add explicit return with type |
| `Incompatible default for argument` | Use `Optional[T]` for nullable args |
| `Missing type parameters for generic type` | Specify type params: `List[str]` not `List` |
| `Cannot determine type of` | Add explicit type annotation |
| `Argument N has incompatible type` | Fix type mismatch or add cast |
| `Module has no attribute` | Add type stubs or ignore with `# type: ignore` |

## Type Checking Philosophy

1. **No compromises**: Every function, every variable, every return value must be typed.
2. **No implicit Any**: If you need Any, declare it explicitly and document why.
3. **Documentation is mandatory**: Every public function needs a complete docstring.
4. **Fail loudly**: Better to catch type errors at check-time than runtime.
5. **Be specific**: `List[str]` is better than `list`, `Dict[str, int]` is better than `dict`.

Remember: In the church of static typing, there is no forgiveness for missing type hints!