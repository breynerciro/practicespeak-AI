export interface Topic {
  id: string
  label: string
  icon: string
}

export const NOVA_TOPICS: Topic[] = [
  { id: 'travel', label: 'Viajes', icon: 'plane' },
  { id: 'daily routine', label: 'Rutina diaria', icon: 'sunrise' },
  { id: 'food and cooking', label: 'Comida', icon: 'utensils' },
  { id: 'hobbies and free time', label: 'Hobbies', icon: 'palette' },
  { id: 'family', label: 'Familia', icon: 'users' },
  { id: 'work and studies', label: 'Trabajo y estudios', icon: 'briefcase' },
  { id: 'weather and seasons', label: 'Clima', icon: 'cloud-sun' },
  { id: 'movies and series', label: 'Películas', icon: 'clapperboard' },
  { id: 'sports', label: 'Deportes', icon: 'trophy' },
  { id: 'music', label: 'Música', icon: 'music' },
  { id: 'technology and gadgets', label: 'Tecnología', icon: 'cpu' },
  { id: 'animals and pets', label: 'Animales', icon: 'paw' },
  { id: 'shopping and clothes', label: 'Compras', icon: 'shirt' },
  { id: 'health and fitness', label: 'Salud', icon: 'dumbbell' },
  { id: 'birthdays and celebrations', label: 'Celebraciones', icon: 'cake' },
  { id: 'books and reading', label: 'Libros', icon: 'book-open' },
  { id: 'nature and the environment', label: 'Naturaleza', icon: 'leaf' },
  { id: 'cars and transport', label: 'Coches', icon: 'car' },
  { id: 'house and home', label: 'Hogar', icon: 'home' },
  { id: 'weekend plans', label: 'Fin de semana', icon: 'calendar' },
  { id: '', label: 'Sorpréndeme', icon: 'sparkles' },
]

export function topicLabel(name: string): string {
  const found = NOVA_TOPICS.find((t) => t.id && t.id === name.toLowerCase())
  return found ? found.label : name
}

export function topicIcon(name: string): string {
  const found = NOVA_TOPICS.find((t) => t.id && t.id === name.toLowerCase())
  return found ? found.icon : 'target'
}