import unittest
from youtubeClass import Youtubedl


class TestYoutubedl(unittest.TestCase):

    def test_create_folder(self):
        example = 'ut2'
        result = Youtubedl.createFolder(self, folder=example)
        self.assertEqual(result, None)


if __name__ == '__main__':
    if __name__ == '__main__':
        unittest.main()
