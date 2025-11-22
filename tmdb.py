import aiohttp
from config import *

async def get_by_name(movie_name, release_year):
    tmdb_search_url = f'https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={movie_name}'
    if TMDB_API_KEY:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(tmdb_search_url) as search_response:
                    search_data = await search_response.json()

                    if search_data['results']:
                        matching_results = []
                        if release_year:
                            matching_results = [
                                result for result in search_data['results']
                                if ('release_date' in result and result['release_date'][:4] == str(release_year)) or
                                ('first_air_date' in result and result['first_air_date'][:4] == str(release_year))
                            ]

                        if not matching_results and search_data['results']:
                            # If no match by year or year not provided, pick the first result
                            matching_results = [search_data['results'][0]]

                        if matching_results:
                            result = matching_results[0]
                            media_type = result['media_type']
                            tmdb_id = result['id']
                            
                            tmdb_movie_image_url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images?api_key={TMDB_API_KEY}&language=en-US&include_image_language=en,hi'
                            tmdb_external_ids_url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}'

                            poster_url = None
                            imdb_id = None

                            # Fetch Images
                            async with session.get(tmdb_movie_image_url) as movie_response:
                                movie_images = await movie_response.json()
                                # Use the backdrop_path or poster_path
                                poster_path = None
                                if 'backdrops' in movie_images and movie_images['backdrops']:
                                    poster_path = movie_images['backdrops'][0]['file_path']
                                                            
                                elif 'poster_path' in result and result['poster_path']:
                                    poster_path = result['poster_path']

                                if poster_path:
                                    poster_url = f"https://image.tmdb.org/t/p/original{poster_path}"

                            # Fetch External IDs (IMDb)
                            async with session.get(tmdb_external_ids_url) as external_ids_response:
                                external_ids = await external_ids_response.json()
                                imdb_id = external_ids.get('imdb_id')

                            return poster_url, imdb_id

            return None, None  # No matching results found
        except Exception as e:
            logger.error(f"Error fetching TMDb ID: {e}")
            return None, None
    return None, None