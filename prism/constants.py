# This file is part of Prism.
#
# Prism is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Prism is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Prism.  If not, see <https://www.gnu.org/licenses/>.

APPNAME = 'Prism'
APPNAME_FULL = f'{APPNAME} Design Inspiration Board'
VERSION = '0.1.0'
WEBSITE = 'https://github.com/rbreu/prism'
COPYRIGHT = 'Copyright © 2021-2024 Rebecca Breu'

CHANGED_SYMBOL = '✎'

COLORS = {
    # Qt palette — Apple dark theme mapping:
    'Active:Base': (28, 28, 30),
    'Active:AlternateBase': (36, 36, 38),
    'Active:Window': (28, 28, 30),
    'Active:Button': (44, 44, 46),
    'Active:Text': (245, 245, 247),
    'Active:HighlightedText': (255, 255, 255),
    'Active:WindowText': (245, 245, 247),
    'Active:ButtonText': (245, 245, 247),
    'Active:Highlight': (10, 132, 255),
    'Active:Link': (10, 132, 255),

    'Disabled:Base': (28, 28, 30),
    'Disabled:Window': (28, 28, 30, 50),
    'Disabled:WindowText': (120, 120, 120),
    'Disabled:Light': (0, 0, 0, 0),
    'Disabled:Text': (140, 140, 140),

    # Prism specific:
    'Scene:Selection': (30, 30, 32),
    'Scene:Canvas': (28, 28, 30),
    'Scene:Text': (245, 245, 247),
}
