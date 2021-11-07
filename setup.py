from distutils.core import setup
import setup_translate

pkg = 'Extensions.EPGImportFilter'
setup(name='enigma2-plugin-extensions-epgimportfilter',
       version='1.12',
       description='EPGImportFilter',
       package_dir={pkg: 'plugin'},
       packages=[pkg],
       package_data={pkg:
           ['plugin.png', 'locale/*/LC_MESSAGES/*.mo']},
       cmdclass=setup_translate.cmdclass, # for translation
      )
