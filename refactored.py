import pygame
import random
import math
from enum import Enum
from typing import List, Tuple, Optional
from dataclasses import dataclass
import time
import tracemalloc

# Initialize Pygame
pygame.init()

# Constants
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 160, 255)
YELLOW = (255, 255, 0)
PURPLE = (147, 0, 211)
DARK_OVERLAY = (0, 0, 0, 128)  # Semi-transparent black

@dataclass
class CreatureType:
    color: Tuple[int, int, int]
    points: int
    radius: int
    nocturnal: bool
    visibility_duration: int  # in milliseconds
    spawn_weight: int

class GameState(Enum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"

class Hunter:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.speed = 5
        self.base_detection_radius = 200  # Increased from 150
        self.detection_radius = self.base_detection_radius
        self.stealth_mode = False
        self.stealth_cooldown = 0
        self.stealth_duration = 3000  # 3 seconds
        self.stealth_recovery = 5000  # 5 seconds
        self.score = 0
        self.size = 20  # Player size
        self.initial_x = x # Store the starting position of the player
        self.initial_y = y
        self.distance_traveled = 0

    def move(self, keys):
        dx = 0
        dy = 0
        if keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_s]: dy += 1
        if keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_d]: dx += 1
        
        # Normalize diagonal movement
        if dx != 0 and dy != 0:
            dx *= 0.707
            dy *= 0.707
            
        speed = self.speed * (0.5 if self.stealth_mode else 1)
        
        new_x = max(self.size, min(SCREEN_WIDTH - self.size, self.x + dx * speed))
        new_y = max(self.size, min(SCREEN_HEIGHT - self.size, self.y + dy * speed))
        
        # Calculate distance moved
        self.distance_traveled += math.sqrt((new_x - self.x)**2 + (new_y-self.y)**2)
        self.x = new_x
        self.y = new_y


    def toggle_stealth(self, current_time):
        if not self.stealth_mode and current_time > self.stealth_cooldown:
            self.stealth_mode = True
            self.detection_radius = self.base_detection_radius * 0.4
            self.stealth_cooldown = current_time + self.stealth_duration + self.stealth_recovery
        elif self.stealth_mode and current_time > self.stealth_cooldown - self.stealth_recovery:
            self.stealth_mode = False
            self.detection_radius = self.base_detection_radius

    def update(self, current_time):
        if self.stealth_mode and current_time > self.stealth_cooldown - self.stealth_recovery:
            self.stealth_mode = False
            self.detection_radius = self.base_detection_radius

class Creature:
    def __init__(self, x: int, y: int, creature_type: CreatureType):
        self.x = x
        self.y = y
        self.type = creature_type
        self.spawn_time = pygame.time.get_ticks()
        self.visible = not creature_type.nocturnal
        self.last_visibility_toggle = self.spawn_time

    def update(self, current_time: int):
        if self.type.nocturnal:
            if current_time - self.last_visibility_toggle >= self.type.visibility_duration:
                self.visible = not self.visible
                self.last_visibility_toggle = current_time

    def is_visible(self, hunter: Hunter) -> bool:
        dx = self.x - hunter.x
        dy = self.y - hunter.y
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= hunter.detection_radius and self.visible

class Predator:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.speed = 2.5
        self.radius = 25  # Increased size for better visibility
        self.detection_radius = 250
        self.chasing = False
        self.target: Optional[Tuple[float, float]] = None
        self.visible = False

    def update(self, hunter: Hunter):
        dx = hunter.x - self.x
        dy = hunter.y - self.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < self.detection_radius and not hunter.stealth_mode:
            self.chasing = True
            self.target = (hunter.x, hunter.y)
        elif self.chasing and hunter.stealth_mode:
            self.chasing = False
            self.target = None

        if self.chasing and self.target:
            dx = self.target[0] - self.x
            dy = self.target[1] - self.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                self.x += (dx / dist) * self.speed
                self.y += (dy / dist) * self.speed

        self.visible = dist <= hunter.detection_radius # Changed this line

    def is_visible(self, hunter:Hunter) -> bool:
        dx = self.x - hunter.x
        dy = self.y - hunter.y
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= hunter.detection_radius

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Hunter's Halo")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        
        self.state = GameState.MENU
        self.level_time = 60  # seconds
        self.time_remaining = self.level_time
        self.start_time = 0
        
        self.hunter = Hunter(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        self.creatures: List[Creature] = []
        self.predators: List[Predator] = []

        self.time_data = []

        self.potential_predator_spawns = []
        self.predator_distances = []

        num_spawn_locations = 50
        spawn_radius = 500
        for _ in range(num_spawn_locations):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(200, spawn_radius)
            x = self.hunter.x + math.cos(angle) * distance
            y = self.hunter.y + math.sin(angle) * distance
            self.potential_predator_spawns.append((x, y))
        
        self.creature_types = [
            CreatureType(BLUE, 10, 15, False, 0, 5),    # Common
            CreatureType(GREEN, 20, 20, False, 0, 3),   # Uncommon
            CreatureType(PURPLE, 50, 25, True, 2000, 1) # Rare nocturnal
        ]
        self.num_spawn_locations = 50
        self.last_spawn_time = 0
        self.score_delay = 0

    def precomputed_spawning_refactored(self):
        spawn_threshold = 200  
        min_spacing = 100   

        current_time = pygame.time.get_ticks()

        if len(self.predators) >= self.num_spawn_locations or current_time - self.last_spawn_time < 2000 or (self.hunter.x == 512 and self.hunter.y == 384):
            return

        for spawn_location in self.potential_predator_spawns:

            dist_to_hunter = math.sqrt((spawn_location[0] - self.hunter.x) ** 2 + (spawn_location[1] - self.hunter.y) ** 2)

            if dist_to_hunter < spawn_threshold:
                too_close = False
                for predator in self.predators:
                    dist_to_predator = math.sqrt((spawn_location[0] - predator.x) ** 2 + (spawn_location[1] - predator.y) ** 2)
                    if dist_to_predator < min_spacing:
                        too_close = True
                        break
                
                if not too_close:

                    # Ensures that cooldown period is maintained and prevent premature spawns
                    self.last_spawn_time = current_time
                    
                    self.potential_predator_spawns.remove(spawn_location)
                    self.predators.append(Predator(spawn_location[0], spawn_location[1]))
                    break

    def check_collisions(self):
        # Check creature captures
        for creature in self.creatures[:]:
            dx = self.hunter.x - creature.x
            dy = self.hunter.y - creature.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < self.hunter.detection_radius and creature.visible:
                self.hunter.score += creature.type.points
                self.creatures.remove(creature)

        # Check predator collisions
        for predator in self.predators:
            dx = self.hunter.x - predator.x
            dy = self.hunter.y - predator.y
            dist = math.sqrt(dx * dx + dy * dy)


            if dist < predator.radius + self.hunter.size:
                self.state = GameState.GAME_OVER
                self.hunter.score += int(self.hunter.distance_traveled/100)

    def draw(self):
        # Clear screen with a dark background
        self.screen.fill((20, 20, 30))  # Dark blue-gray background
        
        # Draw detection radius
        pygame.draw.circle(self.screen, (40, 40, 60), 
                         (int(self.hunter.x), int(self.hunter.y)),
                         int(self.hunter.detection_radius),
                         2)  # Just the outline
        
        # Draw visible creatures
        for creature in self.creatures:
            if creature.is_visible(self.hunter):
                pygame.draw.circle(self.screen, creature.type.color,
                                 (int(creature.x), int(creature.y)),
                                 creature.type.radius)
                # Add a glowing effect
                pygame.draw.circle(self.screen, creature.type.color,
                                 (int(creature.x), int(creature.y)),
                                 creature.type.radius + 5, 2)

        # Draw visible predators
        for predator in self.predators:
            if predator.is_visible(self.hunter):
                # Draw predator body
                pygame.draw.circle(self.screen, RED,
                                 (int(predator.x), int(predator.y)),
                                 predator.radius)
                # Add threatening glow effect
                pygame.draw.circle(self.screen, (255, 100, 100),
                                 (int(predator.x), int(predator.y)),
                                 predator.radius + 8, 2)

        # Draw player
        player_color = (100, 100, 100) if self.hunter.stealth_mode else WHITE
        pygame.draw.circle(self.screen, player_color,
                         (int(self.hunter.x), int(self.hunter.y)), 
                         self.hunter.size)
        # Add player glow effect
        glow_radius = self.hunter.size + 5
        pygame.draw.circle(self.screen, player_color,
                         (int(self.hunter.x), int(self.hunter.y)),
                         glow_radius, 2)

        # Draw HUD
        time_text = self.font.render(f"Time: {int(self.time_remaining)}s", True, WHITE)
        stealth_text = self.font.render("STEALTH ACTIVE" if self.hunter.stealth_mode else "", True, WHITE)
        
        self.screen.blit(time_text, (10, 50))
        self.screen.blit(stealth_text, (SCREEN_WIDTH - 200, 10))

        if self.state == GameState.MENU:
            title_text = self.font.render("Hunter's Halo", True, WHITE)
            menu_text = self.font.render("Press SPACE to start", True, WHITE)
            controls_text = self.font.render("WASD to move, SHIFT for stealth", True, WHITE)
            
            self.screen.blit(title_text, (SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 50))
            self.screen.blit(menu_text, (SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2))
            self.screen.blit(controls_text, (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 + 50))
        elif self.state == GameState.GAME_OVER:
            over_text = self.font.render(f"Game Over! Final Score: {self.hunter.score}", True, WHITE)
            restart_text = self.font.render("Press SPACE to restart", True, WHITE)
            self.screen.blit(over_text, (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2))
            self.screen.blit(restart_text, (SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 50))

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            current_time = pygame.time.get_ticks()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.state in (GameState.MENU, GameState.GAME_OVER):
                            self.state = GameState.PLAYING
                            self.hunter = Hunter(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
                            self.predators.clear()
                            self.time_remaining = self.level_time
                            self.start_time = time.time()
                    elif event.key == pygame.K_LSHIFT and self.state == GameState.PLAYING:
                        self.hunter.toggle_stealth(current_time)

            if self.state == GameState.PLAYING:
                # Update time
                self.time_remaining = self.level_time - (time.time() - self.start_time)
                if self.time_remaining <= 0:
                    self.state = GameState.GAME_OVER
                
                # Update game objects
                keys = pygame.key.get_pressed()
                self.hunter.move(keys)
                self.hunter.update(current_time)
                
                for predator in self.predators:
                    predator.update(self.hunter)
                
                # Spawn new entities
                self.precomputed_spawning_refactored()
                
                self.check_collisions()

                self.score_delay += 1

                if self.score_delay >= 100:
                    self.hunter.score += 5 * len(self.predators)
                    self.score_delay = 0

            self.draw()
            self.clock.tick(FPS)

        pygame.quit()

if __name__ == "__main__":
    game = Game()
    game.run()