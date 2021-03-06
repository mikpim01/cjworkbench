const path = require('path')
const BundleTracker = require('webpack-bundle-tracker')
const MiniCssExtractPlugin = require('mini-css-extract-plugin')

module.exports = {
  context: __dirname,

  // Each page gets its own bundle
  entry: {
    style: './assets/css/style.scss',
    'report-styles': './assets/css/report.scss',
    'embed-styles': './assets/css/embed.scss',
    billing: './assets/js/pages/billing.page',
    plan: './assets/js/pages/plan.page',
    lessons: './assets/js/pages/lessons.page',
    login: './assets/js/pages/login',
    workflows: './assets/js/pages/workflows.page',
    workflow: './assets/js/pages/workflow.page',
    report: './assets/js/pages/report.page',
    embed: './assets/js/pages/embed.page'
  },

  watchOptions: {
    ignored: /node_modules/,
    poll: 500,
    aggregateTimeout: 300
  },

  output: {
    path: path.resolve('./assets/bundles/'),
    filename: '[name]-[contenthash].js'
  },

  devtool: 'source-map',

  plugins: [
    new BundleTracker({ filename: './webpack-stats.json' }),
    new MiniCssExtractPlugin({
      filename: '[name]-[contenthash].css'
    })
  ],

  module: {
    rules: [
      {
        enforce: 'pre',
        test: /\.jsx?$/,
        exclude: /node_modules/,
        loader: 'standard-loader',
        options: {
          parser: 'babel-eslint'
        }
      },
      {
        test: /\.jsx?$/,
        exclude: /node_modules/,
        loader: 'babel-loader', // config is in package.json
        options: {
          cacheDirectory: true
        }
      },
      {
        test: /\.css$/,
        use: [
          MiniCssExtractPlugin.loader,
          'css-loader'
        ]
      },
      {
        test: /\.scss$/,
        use: [
          MiniCssExtractPlugin.loader,
          'css-loader',
          'sass-loader'
        ]
      },
      {
        test: /assets\/icons\/[^/]+\.svg$/,
        use: [
          {
            loader: '@svgr/webpack',
            options: {
              icon: true,
              svgProps: {
                fill: 'currentColor'
              },
              svgoConfig: {
                plugins: [
                  { removeXMLNS: true },
                  { removeAttrs: { attrs: ['stroke', 'fill', 'shape-rendering'] } }
                ]
              }
            }
          }
        ]
      },
      {
        // static files
        test: [
          /\.(gif|png|jpg|woff|woff2)$/,
          /assets\/images\/.*\.svg$/
        ],
        loader: 'url-loader',
        options: {
          limit: 40000,
          name: '[name]-[contenthash].[ext]'
        }
      },
      {
        // i18n translations
        test: /\.po$/,
        loader: '@lingui/loader'
      }
    ]
  },

  resolve: {
    modules: ['node_modules'],
    extensions: ['.js', '.jsx']
  }
}
